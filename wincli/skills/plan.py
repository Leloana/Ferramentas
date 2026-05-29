"""Multi-agent plan mode.

Flow:
  1. Planner            → generates plans/<slug>.md
  2. Task reviewer      → critiques + rewrites vague tasks
  3. User approval      → a / e / r / c
  4. Executor loop      → fresh subagent per task, respects deps
  5. Verifier           → adversarial, must read files to confirm
  6. Final report

All subagents reuse the same model (no swap → no VRAM trash). State
between executors lives in the markdown file itself.
"""

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markup import escape
from rich.table import Table

from subagent import SubAgent

NAME = "plan"
DESCRIPTION = "Multi-agent plan mode: planner → reviewer → approval → executors → verifier"

console = Console()


# ---------- prompts ----------

PLANNER_SYS = """You are a planner. You produce executable action plans for an
AI agent working in a software project.

Output ONLY markdown in this exact structure:

# Plan: <short title>

## Goal
<one paragraph>

## Tasks
- [ ] (id:1, tools:read_file,patch_file) <concrete task referencing real files>
- [ ] (id:2, deps:1, tools:write_file) <next task>
...

## Verification
- [ ] (id:N, deps:..., tools:run_command) <one check — one command or one file read>
- [ ] (id:N+1, deps:..., tools:run_command) <another check>
...

Rules for tasks:
- ALL IDs are integers starting at 1, including verification tasks. Never use letters.
- Verification tasks follow the same numbering sequence as implementation tasks.
- Each verification task checks exactly ONE thing (one command or one file inspection).
- Each task must mention SPECIFIC file paths from the project.
- Each task must be doable in 1-3 tool calls.
- Each task must have a verb (create, modify, replace, add, remove, run, verify).
- Declare deps: comma-separated ids of tasks that must finish first.
- Declare tools: which of read_file, write_file, patch_file, list_dir,
  search_file, run_command, http_get the executor will need. Be minimal.
  NOTE: run_command is NON-BLOCKING (fire-and-forget, no output).
- Use 3-8 tasks total (implementation + verification). Group tiny related actions.

NO prose outside the sections. NO meta-commentary."""


REVIEWER_SYS = """You are a critical task reviewer. You receive a markdown
plan produced by a planner. Your job is to harden it.

For each task, check:
  - Does it mention specific files? If not, FIX it.
  - Is it doable in 1-3 tool calls? If too big, SPLIT it. If too small, MERGE.
  - Are deps correct? Add missing deps.
  - Are tools minimal? Remove unused ones.
  - Is it a verb-action? Rewrite vague tasks like "implement logging" to
    "add get_logger() function in logging_setup.py".

Output the REVISED markdown only, same format as input. Keep the same
overall structure. Be aggressive — assume the planner was sloppy."""


EXECUTOR_SYS = """You are an executor sub-agent. You work on ONE specific task
from a larger plan. You have a restricted set of tools.

TOOL CALL FORMAT — always use exactly this structure, inside a markdown fence:
```json
{"tool": "<name>", "args": {"path": "<absolute_path>", ...}}
```

CRITICAL ARG NAMES (use these exactly, no variations):
  read_file:   {"path": "<abs_path>"}
  write_file:  {"path": "<abs_path>", "content": "<text>"}
  patch_file:  {"path": "<abs_path>", "old_str": "...", "new_str": "..."}
  list_dir:    {"path": "<abs_path>"}
  search_file: {"path": "<abs_path>", "query": "<text>"}
  run_command: {"command": "<powershell_command>"}   # ⚠ NON-BLOCKING: fire-and-forget, returns PID

Rules:
1. Use ONLY the tools listed above.
2. One tool call per response. Wait for the result before continuing.
3. ALWAYS use the ABSOLUTE path provided in your task. Never use './', '../', or relative paths.
4. Modifying an existing file → patch_file. Creating a new file → write_file.
5. If patch_file fails (old_str not found), read the file first, then retry with the correct old_str.
6. run_command is NON-BLOCKING — launches in background. Use for fire-and-forget only.
7. When the task is complete, output EXACTLY these two lines and stop:
     SUMMARY: <one-line description of what you changed>
     FILES: <comma-separated absolute paths of every file you wrote or patched>
8. If you cannot complete the task, output EXACTLY this line and stop:
     FAILED: <reason>"""


VERIFIER_SYS = """You are an adversarial verifier. You have READ-ONLY tools.

You receive:
- A completed plan with checkboxes
- A list of absolute file paths the executor claimed to touch (FILES)

Your job: confirm or deny each completed task.

TOOL CALL FORMAT:
```json
{"tool": "read_file", "args": {"path": "<absolute_path>"}}
```

Protocol:
1. For each task marked [x], call read_file on the paths listed in FILES.
   Use the exact paths from FILES — do not guess or reconstruct paths.
2. Confirm a task only if you personally read the file and saw the change.
   Default to "rejected" if you cannot verify.
3. Tasks marked [✗] or [⊘] are already known-failed; just acknowledge them.
4. If read_file returns an error, reject all tasks that depend on that file.
   Include the attempted path in the rejection reason.

When done, output EXACTLY this JSON block and stop:
```json
{
  "verdict": "ok" | "incomplete" | "broken",
  "confirmed": [<task ids>],
  "rejected": [{"id": <N>, "path_attempted": "<abs_path>", "reason": "<why>"}],
  "summary": "<one paragraph>"
}
```

Verdict rules:
- "ok"         → all [x] tasks confirmed
- "incomplete" → some [x] tasks rejected, but no destructive changes found
- "broken"     → a confirmed change breaks existing functionality

Be skeptical. Marked [x] but unverifiable = rejected."""


# ---------- task model ----------

@dataclass
class Task:
    id: int
    description: str
    deps: List[int] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    status: str = "pending"   # pending | done | failed | skipped
    summary: str = ""
    raw_line: str = ""        # original markdown line for replacement


TASK_LINE_RE = re.compile(
    r"^- \[([ x✗⊘])\]\s*(?:\(([^)]*)\)\s*)?(.+)$"
)
# Splits meta like "id:1, deps:2,3, tools:read_file,patch_file" by finding
# each `key:value` where value runs until the next `, key:` or end-of-string.
META_KV_RE = re.compile(r"(\w+)\s*:\s*(.+?)(?=,\s*\w+\s*:|$)")


def parse_tasks(md: str) -> List[Task]:
    """Extract tasks (under ## Tasks AND ## Verification) from markdown."""
    tasks: List[Task] = []
    in_tasks_section = False
    auto_id = 1000  # fallback id for tasks without explicit id
    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            in_tasks_section = (
                "tasks" in stripped.lower() or "verification" in stripped.lower()
            )
            continue
        if not in_tasks_section:
            continue
        m = TASK_LINE_RE.match(stripped)
        if not m:
            continue
        check_mark, meta, desc = m.group(1), m.group(2) or "", m.group(3).strip()
        # parse meta
        tid = None
        deps: List[int] = []
        tools_list: List[str] = []
        for kv in META_KV_RE.finditer(meta):
            k, v = kv.group(1).lower(), kv.group(2).strip()
            if k == "id":
                try:
                    tid = int(v)
                except ValueError:
                    pass
            elif k == "deps":
                for d in v.split(","):
                    d = d.strip()
                    if d.isdigit():
                        deps.append(int(d))
            elif k == "tools":
                tools_list = [t.strip() for t in v.split(",") if t.strip()]
        if tid is None:
            tid = auto_id
            auto_id += 1
        status = {"x": "done", "✗": "failed", "⊘": "skipped", " ": "pending"}[check_mark]
        tasks.append(Task(id=tid, description=desc, deps=deps, tools=tools_list,
                          status=status, raw_line=line))
    return tasks


def topo_order(tasks: List[Task]) -> List[Task]:
    """Stable topological order. Cycles fall back to declaration order."""
    by_id = {t.id: t for t in tasks}
    visited: Set[int] = set()
    order: List[Task] = []

    def visit(t: Task, stack: Set[int]):
        if t.id in visited or t.id in stack:
            return
        stack.add(t.id)
        for d in t.deps:
            if d in by_id:
                visit(by_id[d], stack)
        stack.discard(t.id)
        visited.add(t.id)
        order.append(t)

    for t in tasks:
        visit(t, set())
    return order


def update_task_line(md: str, task: Task) -> str:
    """Replace the task's line in the markdown with updated checkbox + summary."""
    mark = {"done": "x", "failed": "✗", "skipped": "⊘", "pending": " "}[task.status]
    # Reconstruct meta string
    meta_parts = [f"id:{task.id}"]
    if task.deps:
        meta_parts.append("deps:" + ",".join(str(d) for d in task.deps))
    if task.tools:
        meta_parts.append("tools:" + ",".join(task.tools))
    meta = "(" + ", ".join(meta_parts) + ")"
    new_line = f"- [{mark}] {meta} {task.description}"
    if task.summary:
        new_line += f"\n      → {task.summary}"
    # Replace any line matching the same id (or the raw_line as fallback)
    lines = md.splitlines()
    out_lines = []
    skip_next_arrow = False
    for line in lines:
        if skip_next_arrow:
            if line.strip().startswith("→"):
                skip_next_arrow = False
                continue
            skip_next_arrow = False
        if line == task.raw_line or _line_matches_id(line, task.id):
            out_lines.append(new_line)
            skip_next_arrow = True
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def _line_matches_id(line: str, tid: int) -> bool:
    m = TASK_LINE_RE.match(line.strip())
    if not m:
        return False
    meta = m.group(2) or ""
    for kv in META_KV_RE.finditer(meta):
        if kv.group(1).lower() == "id":
            try:
                return int(kv.group(2).strip()) == tid
            except ValueError:
                return False
    return False


# ---------- helpers ----------

def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return (s or "plan")[:60] + ".md"


def _open_editor(path: Path) -> bool:
    """Open the file in the editor and wait for it to close.
    On Windows, default to notepad (ignoring EDITOR env which is usually
    a Unix editor that won't run). Elsewhere, honor EDITOR then fall back
    to vi. Returns True if the file changed."""
    mtime_before = path.stat().st_mtime
    if sys.platform.startswith("win"):
        editor = "notepad"
    else:
        editor = os.environ.get("EDITOR") or "vi"
    console.print(f"[dim]opening {editor} on {path.name}...[/dim]")
    try:
        subprocess.call([editor, str(path)])
    except Exception as e:
        console.print(f"[red]editor failed: {e}[/red]")
        return False
    return path.stat().st_mtime != mtime_before


def _approval(plan_path: Path, content: str) -> Optional[str]:
    """Loop until user approves, edits, rejects, or cancels.
    Returns the final markdown string, or None if cancelled."""
    while True:
        choice = Prompt.ask(
            "[yellow]plan ready[/yellow] — [bold]a[/bold]pprove / "
            "[bold]e[/bold]dit / [bold]r[/bold]eject (re-plan) / "
            "[bold]c[/bold]ancel",
            choices=["a", "e", "r", "c"], default="a",
        ).lower()
        if choice == "a":
            return content
        if choice == "c":
            return None
        if choice == "e":
            if _open_editor(plan_path):
                content = plan_path.read_text(encoding="utf-8")
                console.print(Panel(content[:4000], title="edited plan",
                                    border_style="blue"))
            continue
        if choice == "r":
            return "__REJECT__"


def _build_executor_user_msg(task: Task, plan_md: str, goal: str,
                             done_tasks: List[Task], working_dir: str) -> str:
    summaries = "\n".join(
        f"  - task {t.id}: {t.summary or '(no summary)'}"
        for t in done_tasks if t.status == "done"
    ) or "  (none yet)"
    allowed = task.tools or ["read_file", "write_file", "patch_file",
                             "list_dir", "search_file"]
    return f"""WORKING DIRECTORY (use this as prefix for ALL file paths): {working_dir}

GOAL OF THE OVERALL PLAN:
{goal}

PREVIOUSLY COMPLETED TASKS (for context):
{summaries}

YOUR TASK (id={task.id}):
{task.description}

TOOLS YOU MAY USE: {", ".join(allowed)}

REMINDER: All 'path' args MUST be absolute. Prefix relative paths with: {working_dir}
Example: if file is 'index.html', use path: "{working_dir}/index.html"

When done, output exactly one line starting with `SUMMARY:` then stop.
If you cannot do it, output `FAILED: <reason>` and stop."""


def _extract_summary(content: str) -> Optional[str]:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("SUMMARY:"):
            return line[len("SUMMARY:"):].strip()[:200]
        if line.startswith("FAILED:"):
            return None
    return None


def _extract_failure(content: str) -> Optional[str]:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("FAILED:"):
            return line[len("FAILED:"):].strip()[:200]
    return None


def _extract_goal(md: str) -> str:
    lines = md.splitlines()
    in_goal = False
    goal_lines = []
    for line in lines:
        if line.strip().startswith("##"):
            in_goal = "goal" in line.lower()
            continue
        if in_goal:
            if line.strip():
                goal_lines.append(line.strip())
    return " ".join(goal_lines)[:1000] or "(no goal stated)"


# ---------- main entry ----------

def run(args, ctx):
    user_prompt = (args or "").strip()
    if not user_prompt:
        return {"error": "/plan requires a prompt"}

    model = ctx["model"]
    working_dir = Path(ctx["working_dir"])
    wincli = (ctx.get("wincli_content") or "")[:3000]
    session_log = ctx.get("session_log")

    # ----- 1. PLANNER -----
    console.print(Panel(
        f"[bold]user goal:[/bold] {escape(user_prompt)}",
        title="📋 multi-agent plan", border_style="cyan"))

    planner = SubAgent(
        model=model, system_prompt=PLANNER_SYS,
        tools_whitelist=["read_file", "list_dir", "search_file"],
        num_ctx=8192, label="planner", max_tool_calls=8,
    )
    planner_msg = (f"User request:\n{user_prompt}\n\n"
                   f"Project context (WINCLI.md):\n{wincli}")
    plan_result = planner.run(planner_msg)
    if plan_result["status"] != "ok" or not plan_result["content"]:
        return {"error": f"planner failed: {plan_result['status']}"}

    if session_log:
        session_log.log_step(
            kind="assistant",
            content=f"[plan - planner subagent]: {plan_result.get('content', '')}",
            prompt_tokens=plan_result.get("tokens", {}).get("prompt", 0),
            gen_tokens=plan_result.get("tokens", {}).get("gen", 0),
            elapsed_s=plan_result.get("elapsed_s", 0.0)
        )

    raw_plan = plan_result["content"]

    # ----- 2. REVIEWER -----
    reviewer = SubAgent(
        model=model, system_prompt=REVIEWER_SYS,
        tools_whitelist=[],   # reviewer doesn't need tools
        num_ctx=8192, label="reviewer", max_tool_calls=0,
    )
    review_result = reviewer.run(f"Plan to review:\n\n{raw_plan}")
    if session_log:
        session_log.log_step(
            kind="assistant",
            content=f"[plan - reviewer subagent]: {review_result.get('content', '')}",
            prompt_tokens=review_result.get("tokens", {}).get("prompt", 0),
            gen_tokens=review_result.get("tokens", {}).get("gen", 0),
            elapsed_s=review_result.get("elapsed_s", 0.0)
        )
    revised_plan = review_result["content"] if review_result["status"] == "ok" \
        and review_result["content"] else raw_plan

    # ----- save + display -----
    plans_dir = working_dir / "plans"
    plans_dir.mkdir(exist_ok=True)
    plan_path = plans_dir / _slug(user_prompt)
    plan_path.write_text(revised_plan + "\n", encoding="utf-8")
    console.print(Panel(revised_plan[:4500], title=f"plan → {plan_path.name}",
                        border_style="blue"))

    # ----- 3. APPROVAL -----
    final_plan = _approval(plan_path, revised_plan)
    if final_plan is None:
        return {"status": "cancelled"}
    if final_plan == "__REJECT__":
        console.print("[yellow]re-planning not implemented yet — cancelled.[/yellow]")
        return {"status": "cancelled"}
    # If user edited, reload from disk
    final_plan = plan_path.read_text(encoding="utf-8")

    # ----- 4. PARSE + EXECUTE -----
    tasks = parse_tasks(final_plan)
    if not tasks:
        return {"error": "no tasks parsed from plan"}
    ordered = topo_order(tasks)
    goal = _extract_goal(final_plan)
    by_id = {t.id: t for t in tasks}
    total = len(ordered)

    console.print(Panel(
        f"executing [bold]{total}[/bold] tasks in dependency order\n"
        f"[dim]⚠ executors write files directly — no permission prompts[/dim]",
        title="🔧 executors", border_style="yellow"))

    all_files_touched: Set[str] = set()
    start_exec = time.time()

    for idx, task in enumerate(ordered, start=1):
        # check deps
        failed_deps = [d for d in task.deps
                       if d in by_id and by_id[d].status in ("failed", "skipped")]
        if failed_deps:
            task.status = "skipped"
            task.summary = f"skipped: dep(s) {failed_deps} did not complete"
            console.print(f"[yellow]⊘[/yellow] task {task.id} skipped (deps failed)")
            final_plan = update_task_line(final_plan, task)
            plan_path.write_text(final_plan, encoding="utf-8")
            continue

        done_so_far = [t for t in ordered if t.status == "done"]
        # Always include write_file so executors can create new files
        whitelist = list(task.tools) if task.tools else None
        if whitelist is not None and "write_file" not in whitelist:
            whitelist.append("write_file")
        executor = SubAgent(
            model=model, system_prompt=EXECUTOR_SYS,
            tools_whitelist=whitelist,
            num_ctx=16384, label=f"executor {idx}/{total} (id={task.id})",
            max_tool_calls=15,
        )
        user_msg = _build_executor_user_msg(task, final_plan, goal, done_so_far,
                                            str(working_dir))
        result = executor.run(user_msg)
        if session_log:
            session_log.log_step(
                kind="assistant",
                content=f"[plan - executor task {task.id} subagent]: {result.get('content', '')}",
                prompt_tokens=result.get("tokens", {}).get("prompt", 0),
                gen_tokens=result.get("tokens", {}).get("gen", 0),
                elapsed_s=result.get("elapsed_s", 0.0)
            )

        for fp in result["files_touched"]:
            all_files_touched.add(fp)

        if result["status"] == "ok":
            summary = _extract_summary(result["content"])
            failure = _extract_failure(result["content"])
            if failure:
                task.status = "failed"
                task.summary = failure
            elif summary:
                task.status = "done"
                task.summary = summary
            else:
                # ok but no marker → treat as done with raw tail
                task.status = "done"
                task.summary = (result["content"].splitlines() or [""])[-1][:200]
        else:
            task.status = "failed"
            task.summary = f"{result['status']}: {result['content'][:150]}"

        # Show per-executor outcome
        status_icon  = {"done": "[green]✓[/green]", "failed": "[red]✗[/red]",
                        "skipped": "[yellow]⊘[/yellow]", "pending": "[dim]…[/dim]"}
        files_line = ""
        if result["files_touched"]:
            files_line = "  Files: " + ", ".join(escape(f) for f in result["files_touched"])
        console.print(
            f"{status_icon.get(task.status, '')} task {task.id}: "
            f"{escape(task.summary[:100])}"
            + (f"\n{files_line}" if files_line else "")
        )

        final_plan = update_task_line(final_plan, task)
        plan_path.write_text(final_plan, encoding="utf-8")

    exec_elapsed = time.time() - start_exec

    # ----- 5. VERIFIER -----
    verifier = SubAgent(
        model=model, system_prompt=VERIFIER_SYS,
        tools_whitelist=["read_file", "list_dir", "search_file"],
        num_ctx=8192, label="verifier", max_tool_calls=12,
    )
    files_msg = "\n".join(f"  - {f}" for f in sorted(all_files_touched)) or "  (none)"
    verif_msg = (f"Plan with checkboxes after execution:\n\n{final_plan}\n\n"
                 f"Files touched by executors:\n{files_msg}\n\n"
                 "Verify now. End with the JSON verdict block.")
    verif_result = verifier.run(verif_msg)
    if session_log:
        session_log.log_step(
            kind="assistant",
            content=f"[plan - verifier subagent]: {verif_result.get('content', '')}",
            prompt_tokens=verif_result.get("tokens", {}).get("prompt", 0),
            gen_tokens=verif_result.get("tokens", {}).get("gen", 0),
            elapsed_s=verif_result.get("elapsed_s", 0.0)
        )

    # ----- 6. FINAL REPORT -----
    table = Table(title="plan execution summary", border_style="cyan")
    table.add_column("id", justify="right", style="cyan")
    table.add_column("status")
    table.add_column("description")
    table.add_column("summary", style="dim")
    for t in ordered:
        status_color = {"done": "green", "failed": "red",
                        "skipped": "yellow", "pending": "white"}[t.status]
        table.add_row(str(t.id),
                      f"[{status_color}]{t.status}[/{status_color}]",
                      t.description[:60],
                      (t.summary or "")[:60])
    console.print(table)

    if verif_result["content"]:
        console.print(Panel(verif_result["content"][:3000],
                            title="🔍 verifier", border_style="magenta"))

    done = sum(1 for t in ordered if t.status == "done")
    failed = sum(1 for t in ordered if t.status == "failed")
    skipped = sum(1 for t in ordered if t.status == "skipped")

    console.print(Panel(
        f"✓ done: [green]{done}[/green]  ✗ failed: [red]{failed}[/red]  "
        f"⊘ skipped: [yellow]{skipped}[/yellow]  / {total}\n"
        f"executors elapsed: {exec_elapsed:.1f}s\n"
        f"plan file: {plan_path}",
        title="result", border_style="green" if failed == 0 else "yellow"))

    # Inject into main conversation so the main agent is aware
    history = ctx.get("conversation_history")
    if history is not None:
        history.append({
            "role": "user",
            "content": (f"[PLAN COMPLETED]\n"
                        f"Plan file: plans/{plan_path.name}\n"
                        f"Done: {done}/{total}. Failed: {failed}. Skipped: {skipped}.\n"
                        f"Verifier said:\n{verif_result['content'][:2000]}"),
        })

    return {"status": "ok", "done": done, "failed": failed,
            "skipped": skipped, "plan_path": str(plan_path)}
