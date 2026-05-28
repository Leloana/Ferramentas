"""Multi-round debug mode with context refresh.

Each round is a fresh SubAgent with its own context. If a round doesn't
reach success, it produces a HANDOFF blurb that's passed to the next
round as condensed knowledge — without the inflated history.

Why this shape and not the full plan-style pipeline:
  - No verifier needed: returncode IS the verdict.
  - No planner needed: user already provided command + criterion.
  - The only real win is context refresh between attempts so the agent
    doesn't get tunnel-visioned on failed approaches.
"""

import re

from rich.console import Console
from rich.panel import Panel
from rich.markup import escape

from subagent import SubAgent

NAME = "debug"
DESCRIPTION = "Multi-round debug loop with context refresh between rounds"

console = Console()


ROUND_SYS = """You are debugging code. You have ONE goal: make the command
succeed against the criterion. You have these tools: run_command,
read_file, write_file, patch_file, list_dir, search_file.

Command to run:
{command}

Success criterion (interpret strictly):
{criterion}

Protocol:
1. Run the command with run_command.
2. Inspect stdout / stderr / returncode.
3. If the criterion is MET → output exactly `DEBUG SUCCESS` on its own
   line and stop. No more tool calls.
4. Otherwise diagnose, edit code (patch_file preferred), and go to 1.
5. PowerShell syntax. patch_file uses the active variant declared in
   tools.py — read_file output includes line numbers.

If you cannot succeed within your tool-call budget, end your final
message with a single block exactly like this:

```handoff
TRIED: <comma-separated list of approaches attempted>
LAST_ERROR: <the error message that's still happening>
FILES_TOUCHED: <comma-separated paths you modified>
HYPOTHESIS: <your best guess about the root cause>
NEXT: <what a fresh attempt should try differently>
```

Do not write a handoff if you achieved DEBUG SUCCESS.
{handoff_section}"""


HANDOFF_PREFIX = """

PREVIOUS ROUNDS ALREADY TRIED (do NOT repeat these approaches):
{handoffs}

A fresh round starts now. Use the hypothesis and NEXT suggestions from
prior rounds as your starting point. Be willing to challenge their
assumptions if the evidence warrants."""


HANDOFF_RE = re.compile(r"```handoff\s*(.*?)\s*```", re.DOTALL)
SUCCESS_RE = re.compile(r"^\s*DEBUG\s+SUCCESS\s*$", re.MULTILINE)


def _extract_handoff(content: str) -> str:
    m = HANDOFF_RE.search(content)
    if m:
        return m.group(1).strip()
    return ""


def _format_handoffs(handoffs):
    return "\n\n".join(
        f"-- Round {i+1} --\n{h}" for i, h in enumerate(handoffs)
    )


def run(args, ctx):
    raw = (args or "").strip()
    if "|||" not in raw:
        return {"error": "usage: /skill debug <command> ||| <success criterion>"}
    command, _, criterion = raw.partition("|||")
    command, criterion = command.strip(), criterion.strip()
    if not command or not criterion:
        return {"error": "both command and criterion are required"}

    model = ctx["model"]
    max_rounds = 3
    max_iters_per_round = 6  # tool calls per round

    console.print(Panel(
        f"[bold]command:[/bold]   {escape(command)}\n"
        f"[bold]criterion:[/bold] {escape(criterion)}\n"
        f"[dim]rounds: up to {max_rounds} × {max_iters_per_round} tool calls each[/dim]",
        title="🐛 multi-round debug", border_style="cyan"))

    handoffs = []  # list of handoff strings from previous rounds
    success = False
    final_content = ""

    for round_idx in range(1, max_rounds + 1):
        handoff_section = ""
        if handoffs:
            handoff_section = HANDOFF_PREFIX.format(
                handoffs=_format_handoffs(handoffs))

        console.print(Panel(
            f"starting round [bold]{round_idx}/{max_rounds}[/bold]" +
            (f"  [dim]({len(handoffs)} handoff(s) in context)[/dim]" if handoffs else ""),
            border_style="yellow"))

        system_prompt = ROUND_SYS.format(
            command=command, criterion=criterion,
            handoff_section=handoff_section)

        debugger = SubAgent(
            model=model, system_prompt=system_prompt,
            tools_whitelist=["run_command", "read_file", "write_file",
                             "patch_file", "list_dir", "search_file"],
            num_ctx=8192,
            label=f"debugger round {round_idx}",
            max_tool_calls=max_iters_per_round,
            max_strikes=3,
        )

        result = debugger.run(
            f"Begin debugging now. Run the command first, then iterate.")
        final_content = result["content"]

        if SUCCESS_RE.search(final_content):
            success = True
            console.print(Panel(
                f"[green]✓ DEBUG SUCCESS on round {round_idx}[/green]",
                border_style="green"))
            break

        # Extract handoff for the next round
        handoff = _extract_handoff(final_content)
        if not handoff:
            # Subagent ended without success and without handoff — build a
            # minimal one from what we know so we still hand something to
            # the next round.
            tail = final_content.strip().splitlines()[-5:] if final_content else []
            last_errors = []
            for c in result["tool_calls"][-3:]:
                if not c["success"]:
                    res = c["result"]
                    err = res.get("error") or res.get("stderr") or ""
                    if err:
                        last_errors.append(err[:200])
            handoff = (
                f"TRIED: (no explicit handoff from round {round_idx})\n"
                f"LAST_ERROR: {(last_errors[-1] if last_errors else 'unknown')}\n"
                f"FILES_TOUCHED: {', '.join(result['files_touched']) or '(none)'}\n"
                f"HYPOTHESIS: (round did not produce one)\n"
                f"NEXT: try a different approach"
            )

        handoffs.append(handoff)
        console.print(Panel(handoff, title=f"handoff round {round_idx}",
                            border_style="dim cyan"))

        if result["status"] == "stuck":
            console.print(f"[yellow]round {round_idx} tripped strikes — moving on[/yellow]")
        elif result["status"] == "max_calls":
            console.print(f"[yellow]round {round_idx} hit max tool calls[/yellow]")

    # Final report
    if success:
        title, color = "DEBUG SUCCESS", "green"
        body = f"criterion met on round {round_idx} of {max_rounds}."
    else:
        title, color = "DEBUG STUCK", "red"
        body = (f"after {max_rounds} rounds the criterion was not met.\n\n"
                f"handoffs accumulated:\n\n{_format_handoffs(handoffs)}")

    console.print(Panel(body, title=title, border_style=color))

    history = ctx.get("conversation_history")
    if history is not None:
        history.append({
            "role": "user",
            "content": (f"[DEBUG {'SUCCESS' if success else 'STUCK'}]\n"
                        f"command: {command}\n"
                        f"criterion: {criterion}\n"
                        f"rounds used: {round_idx if success else max_rounds}\n"
                        + (f"final attempt notes:\n{final_content[:1500]}"
                           if not success else "")),
        })

    return {
        "status": "ok" if success else "stuck",
        "rounds_used": round_idx if success else max_rounds,
        "handoffs": handoffs,
    }
