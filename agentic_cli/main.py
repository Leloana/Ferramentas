"""Agentic CLI entry point.

Slash commands:
  /init                  → regenerate WINCLI.md
  /mode [args]           → show or change op/perm mode
  /context               → session dashboard
  /skill <name> [args]   → invoke a skill from skills/
  /skills                → list available skills
  /plan <prompt>         → shortcut for /skill plan ...
  /debug <cmd> ||| <ok>  → shortcut for /skill debug ...
  /reflect [hint]        → shortcut for /skill reflect ...
  exit / quit            → leave

The shell prompt is enriched as:
  [<cwd_basename> | <model> | <op>/<perm> | <session_tokens>] >
"""

import sys
from pathlib import Path

import ollama
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.history import FileHistory

from agent import run_agent_loop
from modes import SessionState, handle_mode_command
from persist import SessionLog, list_sessions, load_session, rebuild_history
from snapshot import SnapshotManager
import skills as skills_pkg
import tools

console = Console()
# No signal handler: default KeyboardInterrupt raise lets each turn cancel
# without killing the process. Top-level pt_prompt catches it to exit.


def load_wincli_context(working_dir):
    p = working_dir / "WINCLI.md"
    if p.exists():
        try:
            return p.read_text(encoding="utf-8"), True
        except Exception:
            return None, False
    return None, False


def build_system_prompt(working_dir, wincli_content):
    """Core tools only — skills are surfaced lazily via /skill ..."""
    wincli_section = ""
    if wincli_content:
        wincli_section = (f"\nBASE PROJECT CONTEXT (WINCLI.md):\n"
                          f"---\n{wincli_content}\n---\n")
    return f"""You are an agentic assistant with access to the following tools.

WORKING DIRECTORY: {working_dir}
All file paths are relative to this directory unless absolute.
{wincli_section}
Core tools:
- run_command: {{"command": "<powershell>"}}
- read_file:   {{"path": "<file>"}}            # returns numbered lines
- write_file:  {{"path": "<file>", "content": "<text>"}}
- patch_file:  see active variant below
- list_dir:    {{"path": "<dir>"}}
- search_file: {{"path": "<file>", "query": "<str>"}}
- http_get:    {{"url": "<url>"}}

patch_file active variant: {tools.ACTIVE_PATCH}
  v1: {{"path","old_str","new_str"}}                   — first unique match
  v2: {{"path","old_str","new_str","context_before","context_after"}}
  v3: {{"path","start_line","end_line","new_content"}} — uses line numbers
       from read_file's numbered output

To call a tool, output ONLY this JSON block:
```json
{{"tool": "<name>", "args": {{...}}}}
```

RULES:
1. One tool per turn.
2. After a tool, wait for the result before calling the next.
3. When you have the final answer, write it directly WITHOUT a JSON block.
4. Commands are PowerShell (`Get-ChildItem`, not `ls`).
5. Modifying an existing file → patch_file. Creating new → write_file.
6. If WINCLI.md is loaded, follow it.
7. Final answer = short summary (created/modified/ran). No prose unless asked.
8. Thinking is allowed inside <think>...</think>; the user sees it but it
   won't be parsed for tool calls.
"""


def render_prompt(working_dir, model, state, session_log):
    cwd = working_dir.name
    totals = session_log.session_totals()
    consumed = totals["prompt_tokens"] + totals["gen_tokens"]
    if state.focus:
        # focus mode: minimal prompt, keep only token cost (required)
        return f"\n[{consumed:,} t] › "
    return f"\n[{cwd} | {model} | {state.mode_label()} | {consumed:,} t] > "


def show_context(state, session_log, model, working_dir, wincli_loaded,
                 conversation_history, snapshot_mgr):
    totals = session_log.session_totals()
    table = Table(title="session context", border_style="cyan", show_header=False)
    table.add_column("key", style="cyan")
    table.add_column("value", style="white")
    table.add_row("session_id", session_log.session_id)
    if session_log.data.get("resumed_from"):
        table.add_row("resumed_from", session_log.data["resumed_from"])
    table.add_row("model", model)
    table.add_row("op_mode / perm_mode", state.mode_label())
    table.add_row("working_dir", str(working_dir))
    table.add_row("WINCLI.md loaded", "yes" if wincli_loaded else "no")
    table.add_row("patch_file variant", tools.ACTIVE_PATCH)
    table.add_row("turns", str(session_log.turn_count()))
    table.add_row("messages in history", str(len(conversation_history)))
    table.add_row("prompt tokens (Σ)", f"{totals['prompt_tokens']:,}")
    table.add_row("gen tokens (Σ)", f"{totals['gen_tokens']:,}")
    table.add_row("elapsed (Σ)", f"{totals['elapsed_s']:.1f}s")
    table.add_row("persist file", str(session_log.path))
    table.add_row("undo stack depth", str(len(snapshot_mgr.stack)))
    console.print(table)

    # Diff stats
    diffs = snapshot_mgr.diff_stats()
    if diffs:
        diff_table = Table(title="files modified this session",
                           border_style="green")
        diff_table.add_column("file")
        diff_table.add_column("+", style="green", justify="right")
        diff_table.add_column("-", style="red", justify="right")
        diff_table.add_column("note", style="dim")
        for d in sorted(diffs, key=lambda x: -(x["added"] + x["removed"])):
            note = "new" if d["was_new"] else ""
            diff_table.add_row(d["path"], str(d["added"]), str(d["removed"]), note)
        console.print(diff_table)

    sk_table = Table(title="available skills", border_style="magenta", show_header=True)
    sk_table.add_column("name", style="magenta")
    sk_table.add_column("description")
    for name, desc in sorted(skills_pkg.index().items()):
        sk_table.add_row(name, desc)
    console.print(sk_table)

    if state.always_allow_tools or state.always_allow_paths:
        console.print(f"[dim]always-allow tools: {sorted(state.always_allow_tools)}[/dim]")
        console.print(f"[dim]always-allow paths: {dict(state.always_allow_paths)}[/dim]")


def handle_resume(arg, working_dir, model_default):
    """Returns (session_data, model) or (None, None) on cancel."""
    arg = (arg or "").strip()
    if not arg:
        sessions = list_sessions(working_dir, limit=10)
        if not sessions:
            console.print("[yellow]no sessions found in .persist/[/yellow]")
            return None, None
        table = Table(title="recent sessions", border_style="cyan")
        table.add_column("#", justify="right")
        table.add_column("id")
        table.add_column("model")
        table.add_column("turns", justify="right")
        table.add_column("started_at", style="dim")
        for i, s in enumerate(sessions, start=1):
            table.add_row(str(i), s["id"], s["model"], str(s["turns"]),
                          s["started_at"][:19])
        console.print(table)
        choice = Prompt.ask("pick # (or [c]ancel)",
                            choices=[str(i+1) for i in range(len(sessions))] + ["c"],
                            default="1")
        if choice == "c":
            return None, None
        data = load_session(working_dir, sessions[int(choice) - 1]["id"])
        return data, sessions[int(choice) - 1]["model"]

    data = load_session(working_dir, arg)
    if not data:
        console.print(f"[red]no session matching '{arg}'[/red]")
        return None, None
    return data, data.get("model", model_default)


def handle_undo(arg, snapshot_mgr):
    try:
        n = int(arg.strip()) if arg.strip() else 1
    except ValueError:
        console.print("[red]usage: /undo [N][/red]")
        return
    if not snapshot_mgr.stack:
        console.print("[yellow]nothing to undo[/yellow]")
        return
    reverted = snapshot_mgr.undo_last(n)
    if not reverted:
        console.print("[yellow]undo stack was empty[/yellow]")
        return
    for e in reverted:
        verb = "deleted" if not e.existed_before else "restored"
        console.print(f"[green]↶[/green] {verb} {e.path} (was {e.action} #{e.seq})")


def list_skills():
    table = Table(title="skills", border_style="magenta")
    table.add_column("name", style="magenta")
    table.add_column("description")
    for n, d in sorted(skills_pkg.index().items()):
        table.add_row(n, d)
    console.print(table)


def main():
    console.print(Panel.fit("[bold magenta]Agentic CLI — Ollama[/bold magenta]",
                            style="bold magenta"))
    working_dir = Path.cwd().resolve()
    console.print(Panel(f"[cyan]{working_dir}[/cyan]", title="working directory",
                        border_style="blue"))

    # Ollama check + model selection
    with console.status("connecting to ollama...", spinner="dots"):
        try:
            models_data = ollama.list()
        except Exception as e:
            console.print(Panel(f"[red]ollama not reachable: {escape(str(e))}[/red]",
                                border_style="red"))
            sys.exit(1)
    available = [m.get("name", m.get("model", "")) for m in models_data.get("models", [])]
    available = [n for n in available if n]
    if not available:
        console.print("[yellow]no models found. run `ollama pull <model>` first.[/yellow]")
        sys.exit(1)

    console.print("[bold]models:[/bold]")
    for i, m in enumerate(available):
        console.print(f"  [cyan]{i+1}[/cyan]. {m}")
    sel = Prompt.ask("select model", choices=[str(i+1) for i in range(len(available))],
                     default="1")
    model = available[int(sel) - 1]

    wincli_content, wincli_loaded = load_wincli_context(working_dir)
    state = SessionState()
    session_log = SessionLog(working_dir, model)
    snapshot_mgr = SnapshotManager(working_dir, session_log.session_id)

    console.print(Panel(
        f"model: [green]{model}[/green]\n"
        f"WINCLI.md: {'loaded' if wincli_loaded else '[yellow]not found — run /init[/yellow]'}\n"
        f"persist: {session_log.path}\n"
        f"mode: {state.mode_label()}  (change via /mode)\n"
        f"skills: {len(skills_pkg.index())} discovered  (list via /skills)\n"
        "commands: /init /mode /focus /context /skills /skill /plan /debug /reflect "
        "/resume /undo  exit",
        title="ready", border_style="green"))

    system_prompt = build_system_prompt(working_dir, wincli_content)
    conversation_history = [{"role": "system", "content": system_prompt}]
    history = FileHistory(str(working_dir / ".history"))

    def trigger_reflect():
        skills_pkg.run("reflect", "", ctx_dict())

    def ctx_dict():
        return {
            "working_dir": working_dir,
            "model": model,
            "wincli_content": wincli_content,
            "conversation_history": conversation_history,
            "session_log": session_log,
            "state": state,
            "snapshot_mgr": snapshot_mgr,
        }

    while True:
        try:
            user_input = pt_prompt(render_prompt(working_dir, model, state, session_log),
                                   history=history)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]goodbye![/yellow]")
            sys.exit(0)

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            console.print("[yellow]goodbye![/yellow]")
            sys.exit(0)

        # ---- slash commands ----
        if user_input.startswith("/"):
            head, _, rest = user_input.partition(" ")
            cmd = head[1:].lower()

            if cmd == "init":
                from init_skill import generate_wincli
                try:
                    if generate_wincli(working_dir, model, session_log=session_log):
                        wincli_content, wincli_loaded = load_wincli_context(working_dir)
                        # rebuild system prompt
                        conversation_history[0] = {
                            "role": "system",
                            "content": build_system_prompt(working_dir, wincli_content),
                        }
                except Exception as e:
                    console.print(Panel(f"[red]init failed: {escape(str(e))}[/red]",
                                        border_style="red"))
                continue

            if cmd == "mode":
                handle_mode_command(state, rest)
                continue

            if cmd == "focus":
                arg = rest.strip().lower()
                if arg in ("on", "1", "true"):
                    state.focus = True
                elif arg in ("off", "0", "false"):
                    state.focus = False
                else:
                    state.focus = not state.focus
                if state.focus:
                    console.print("[dim]focus on — only chat, tools, and tokens.[/dim]")
                else:
                    console.print("[green]focus off — full UI restored.[/green]")
                continue

            if cmd == "context":
                show_context(state, session_log, model, working_dir, wincli_loaded,
                             conversation_history, snapshot_mgr)
                continue

            if cmd == "skills":
                list_skills()
                continue

            if cmd == "resume":
                data, prev_model = handle_resume(rest, working_dir, model)
                if data is None:
                    continue
                # Replace current state with resumed session
                model = prev_model
                conversation_history = rebuild_history(data, system_prompt)
                session_log = SessionLog(working_dir, model,
                                         resumed_from=data.get("session_id"))
                snapshot_mgr = SnapshotManager(working_dir, session_log.session_id)
                console.print(Panel(
                    f"[green]resumed[/green] from {data.get('session_id')}\n"
                    f"replayed {len(data.get('turns', []))} turns "
                    f"({len(conversation_history)} messages in history)\n"
                    f"new session id: {session_log.session_id}",
                    border_style="green"))
                continue

            if cmd == "undo":
                handle_undo(rest, snapshot_mgr)
                continue

            if cmd in ("skill", "plan", "debug", "reflect", "add_skill", "add_tool"):
                # /plan X is sugar for /skill plan X, etc.
                if cmd == "skill":
                    name, _, sk_args = rest.partition(" ")
                else:
                    name, sk_args = cmd, rest
                if not name:
                    console.print("[yellow]usage: /skill <name> [args][/yellow]")
                    continue
                session_log.start_turn(user_input)
                result = skills_pkg.run(name, sk_args, ctx_dict())
                if result.get("error"):
                    console.print(Panel(f"[red]{escape(result['error'])}[/red]",
                                        title=f"/skill {name}", border_style="red"))
                # If the skill injected an instruction into history, let the
                # agent process it.
                last = conversation_history[-1] if conversation_history else None
                if last and last.get("role") == "user" and last.get("content", "").startswith(
                        ("[PLAN MODE]", "[DEBUG MODE", "[REFLECTION]")):
                    try:
                        run_agent_loop(conversation_history, model,
                                       state=state, session_log=session_log,
                                       reflect_callback=trigger_reflect,
                                       snapshot_mgr=snapshot_mgr)
                    except KeyboardInterrupt:
                        console.print("[yellow]skill turn cancelled[/yellow]")
                    except Exception as e:
                        console.print(Panel(f"[red]agent error: {escape(str(e))}[/red]",
                                            border_style="red"))
                continue

            console.print(f"[yellow]unknown command: {head}[/yellow]")
            continue

        # ---- normal turn ----
        session_log.start_turn(user_input)
        conversation_history.append({"role": "user", "content": user_input})
        try:
            run_agent_loop(conversation_history, model,
                           state=state, session_log=session_log,
                           reflect_callback=trigger_reflect,
                           snapshot_mgr=snapshot_mgr)
        except KeyboardInterrupt:
            console.print("[yellow]turn cancelled — session preserved[/yellow]")
        except Exception as e:
            console.print(Panel(f"[red]agent error: {escape(str(e))}[/red]",
                                border_style="red"))


if __name__ == "__main__":
    main()
