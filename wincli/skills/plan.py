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

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from rich.panel import Panel
from rich.markup import escape
from rich.table import Table

from subagent import SubAgent
import ui
from ui import console

NAME = "plan"
DESCRIPTION = "Multi-agent plan mode: planner → reviewer → approval → executors → verifier"


# ---------- prompts ----------

PLANNER_SYS = """You are a planner. You produce executable action plans for an
AI agent working in a software project.

PHASE 1 — EXPLORE (required before writing any plan):
You have access to read_file, list_dir, and search_file. Use them now to gather context.

To call a tool, output ONE ```json block and nothing else. Paths are absolute with
forward slashes "/", never backslashes:
```json
{"tool": "list_dir", "args": {"path": "C:/Users/me/proj"}}
```

Steps:
1. Call list_dir on the WORKING DIRECTORY to see what files exist.
2. If the user's request references a specific file (e.g. "modify app.py", "add feature to server.js"):
   a. Check that the file appears in the listing.
   b. If it does NOT exist, output EXACTLY this line and stop:
        PLAN_ERROR: file '<name>' not found in <working_dir>
   c. If it DOES exist, call read_file on it to understand its current content.
3. Read any other files that are relevant to the request (e.g. config, imports, related modules).
4. Only after exploring, proceed to PHASE 2.

PHASE 2 — PLAN:
Output ONLY the markdown below — no other text, no extra sections, nothing else:

# Plan: <short title>

## Goal
<one paragraph>

## Tasks
- [ ] (id:1, tools:read_file,patch_file) <concrete task with specific file path>
- [ ] (id:2, deps:1, tools:write_file) <next task>

## Verification
- [ ] (id:3, deps:1,2, tools:read_file) Verify index.html exists and contains expected content

STRICT ID RULES — read carefully:
- IDs are GLOBALLY unique integers across BOTH ## Tasks and ## Verification.
- Numbering is one continuous sequence: 1, 2, 3, 4, 5, ...
- NEVER reuse an ID. If ## Tasks has ids 1,2,3, then ## Verification starts at 4.
- Example with 3 impl tasks + 2 verification:
    ## Tasks
    - [ ] (id:1, ...) ...
    - [ ] (id:2, deps:1, ...) ...
    - [ ] (id:3, deps:2, ...) ...
    ## Verification
    - [ ] (id:4, deps:1,2,3, ...) ...
    - [ ] (id:5, deps:4, ...) ...

TASK DESCRIPTION RULES — each description must be specific enough that an executor
can act on it WITHOUT asking any clarifying questions:
- Name the exact file path (e.g. "index.html", not "the file").
- List the KEY technical items to implement: function names, HTML elements, algorithms,
  CSS properties, data structures. Do NOT say "implement the game logic" — say
  "implement collision detection using elastic collision equations, friction=0.985,
   ball radius=10px, cue ball separate from object balls".
- For verification tasks: use read_file to check that the created file exists and
  contains the expected content. Do NOT use run_command for verification — it is
  non-blocking and returns no output, so the executor can never see the result.
  Wrong:  run_command: Test-Path index.html (executor gets only a PID back, can't verify)
  Right:  read_file index.html and confirm key content is present (e.g. "<canvas", "friction")

SCOPE RULE:
- Only create tasks for things the user EXPLICITLY requested. Do NOT invent extra
  deliverables (documentation files, README, changelogs, config files) unless the
  user asked for them.

ANTI-PATTERNS — these are FORBIDDEN and will break execution:
1. DO NOT create a task that just reads or checks if a file exists before writing it.
   Executors verify existence automatically. Jump straight to the write/patch task.
2. DO NOT split a single file's content across multiple write_file tasks.
   write_file OVERWRITES the whole file every time — writing a file in parts destroys
   the previous parts. If one file needs to be created, use EXACTLY ONE task for it.
   Wrong:  task2=write HTML structure, task3=write CSS to same file, task4=write JS to same file
   Right:  task2=write complete index.html with HTML + CSS + JS in one call

STRICTLY FORBIDDEN:
- No extra markdown sections beyond # Plan, ## Goal, ## Tasks, ## Verification.
- No prose before or after the plan.
- No commentary about your decisions."""


REVIEWER_SYS = """You are a plan reviewer. You receive a markdown plan and
output a corrected version.

Check every task in ## Tasks and ## Verification:
  - Does it name a specific file? If not, add the filename.
  - Is it doable in 1-3 tool calls? Too big → split. Too small → merge with a neighbor.
  - Are deps correct and present? Fix missing or wrong deps.
  - Are tools minimal? Drop any tool the task won't actually use.
  - Does the description start with a verb? Rewrite if not.

MANDATORY MERGES — you MUST apply these even if the planner didn't:
  A) SAME-FILE WRITES: If multiple tasks all write_file to the same path, merge them
     into ONE task. write_file overwrites the whole file — separate tasks destroy each
     other's work. One file = one write_file task, containing all the content.
  B) EXISTENCE CHECKS: Remove any task whose only purpose is to read or check if a
     file exists (e.g. "read index.html to see current content", "check if file exists",
     "verify file was created"). Executors do this automatically. Delete these tasks
     entirely and fix deps of downstream tasks to skip the removed id.

  C) run_command IN VERIFICATION: Any ## Verification task that uses run_command must
     be changed to use read_file instead. run_command is NON-BLOCKING — it returns
     only a PID, never the command output, so executors cannot use it to verify anything.
     Replace run_command verification tasks with read_file tasks that check file content.

Check the ID sequence:
  - All IDs must be globally unique integers across BOTH sections.
  - If ## Tasks has ids 1,2,3 and ## Verification also has id 3, renumber
    the verification task to id 4 and update its deps accordingly.
  - The sequence must be gap-free and continuous.

STRICT OUTPUT RULES — violating these will break the system:
  1. Output ONLY the revised markdown plan. Nothing else.
  2. Keep EXACTLY these sections in this order:
       # Plan: ...
       ## Goal
       ## Tasks
       ## Verification
  3. Do NOT add any other section (## Notes, ## Summary, ## Fixes, ## Changes, etc.).
  4. Do NOT add any prose before, after, or between sections.
  5. Do NOT explain what you changed. No commentary. No bullet points outside tasks.
  6. If the plan is already correct, output it unchanged."""


EXECUTOR_SYS = """You are an executor sub-agent. You work on ONE specific task
from a larger plan. You act ONLY by calling tools.

PATHS: every path is absolute and uses forward slashes "/", never backslashes.
  Correct: "C:/Users/me/proj/index.html"   Wrong: "C:\\Users\\me\\proj\\index.html"

TOOLS — this is the COMPLETE list. Use these exact arg keys, no variations:
  read_file:   {"path": "<abs>"}                      → returns lines WITH line numbers
  list_dir:    {"path": "<abs dir>"}
  search_file: {"path": "<abs>", "query": "<text>"}
  write_file:  {"path": "<abs>", "content": "<full file text>"}   → overwrites the WHOLE file
  patch_file:  {"path": "<abs>", "start_line": <int>, "end_line": <int>, "new_content": "<text>"}
                 → replaces lines start_line..end_line (inclusive); get numbers from read_file FIRST
  run_command: {"command": "<powershell>"}   ⚠ NON-BLOCKING: returns a PID only, never output

RESPONSE FORMAT — output ONE ```json block and nothing else when calling a tool:
```json
{"tool": "read_file", "args": {"path": "C:/Users/me/proj/index.html"}}
```

Rules:
1. Use ONLY the tools listed above. ONE tool call per response, then wait for the result.
2. Never repeat a tool call with identical args. If it failed, change something.
3. Creating a new file → write_file. Editing part of an existing file → read_file first, then patch_file with the line numbers you saw.
4. run_command is NON-BLOCKING — fire-and-forget only; never rely on its output.
5. When the task is complete, output EXACTLY these two lines and stop (no json block):
     SUMMARY: <one-line description of what you changed>
     FILES: <comma-separated absolute paths of every file you wrote or patched>
6. If you cannot complete the task, output EXACTLY this line and stop:
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


# ---------- plan validation ----------

_ALLOWED_H2 = {"goal", "tasks", "verification"}


def _validate_and_clean_plan(md: str) -> tuple:
    """Strip non-template sections and report duplicate task IDs.

    Returns (cleaned_md, warnings_list).
    Keeps only: # Plan …, ## Goal, ## Tasks, ## Verification.
    Any other ## section (e.g. ## Critical Fixes Applied) is removed entirely.
    """
    warnings: List[str] = []
    out_lines: List[str] = []
    skipping = False

    for line in md.splitlines():
        stripped = line.strip()
        if stripped.startswith("##") and not stripped.startswith("###"):
            heading = stripped.lstrip("#").strip().lower().split(":")[0].strip()
            if heading in _ALLOWED_H2:
                skipping = False
                out_lines.append(line)
            else:
                title = stripped.lstrip("#").strip()
                warnings.append(f"removed unexpected section '## {title}'")
                skipping = True
            continue
        if stripped.startswith("#") and not stripped.startswith("##"):
            skipping = False
            out_lines.append(line)
            continue
        if not skipping:
            out_lines.append(line)

    cleaned = "\n".join(out_lines).strip()

    # Detect duplicate IDs (non-fatal: warn only — prompts should prevent them)
    tasks = parse_tasks(cleaned)
    seen: Dict[int, str] = {}
    for t in tasks:
        if t.id in seen:
            warnings.append(
                f"duplicate id:{t.id} — '{seen[t.id]}' and '{t.description[:50]}'"
            )
        else:
            seen[t.id] = t.description[:50]

    return cleaned, warnings


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
        options = [
            ("approve", "a"),
            ("edit in editor", "e"),
            ("reject (re-plan)", "r"),
            ("cancel", "c"),
        ]
        choice = ui.select(options, title="plan ready — what to do?", default=0,
                           footer="↑/↓ move · enter select")
        if choice in (None, "c"):
            return None
        if choice == "a":
            return content
        if choice == "e":
            if _open_editor(plan_path):
                content = plan_path.read_text(encoding="utf-8")
                console.print(Panel(content[:4000], title="edited plan",
                                    border_style="blue"))
            continue
        if choice == "r":
            return "__REJECT__"


def _build_executor_user_msg(task: Task, goal: str,
                             done_tasks: List[Task], working_dir: str) -> str:
    summaries = "\n".join(
        f"  - task {t.id}: {t.summary or '(no summary)'}"
        for t in done_tasks if t.status == "done"
    ) or "  (none yet)"
    allowed = task.tools or ["read_file", "write_file", "patch_file",
                             "list_dir", "search_file"]
    wd = working_dir.replace("\\", "/")
    return f"""WORKING DIRECTORY (use this as prefix for ALL file paths): {wd}

GOAL OF THE OVERALL PLAN:
{goal}

PREVIOUSLY COMPLETED TASKS (for context):
{summaries}

YOUR TASK (id={task.id}):
{task.description}

TOOLS YOU MAY USE: {", ".join(allowed)}

REMINDER: All 'path' args MUST be absolute, with forward slashes. Prefix with: {wd}
Example: if file is 'index.html', use path: "{wd}/index.html"

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
        num_ctx=12288, label="planner", max_tool_calls=20,
    )
    planner_msg = (f"WORKING DIRECTORY: {working_dir}\n\n"
                   f"User request:\n{user_prompt}\n\n"
                   f"Project context (WINCLI.md):\n{wincli}")
    plan_result = planner.run(planner_msg)

    # Check for explicit PLAN_ERROR from the planner (file not found, etc.)
    raw_plan_content = plan_result.get("content", "")
    for line in raw_plan_content.splitlines():
        if line.strip().startswith("PLAN_ERROR:"):
            error_msg = line.strip()[len("PLAN_ERROR:"):].strip()
            console.print(Panel(f"[red]{escape(error_msg)}[/red]",
                                title="planner error", border_style="red"))
            return {"error": error_msg}

    if plan_result["status"] != "ok" or not raw_plan_content:
        return {"error": f"planner failed: {plan_result['status']}"}

    if session_log:
        session_log.log_step(
            kind="assistant",
            content=f"[plan - planner subagent]: {plan_result.get('content', '')}",
            prompt_tokens=plan_result.get("tokens", {}).get("prompt", 0),
            gen_tokens=plan_result.get("tokens", {}).get("gen", 0),
            elapsed_s=plan_result.get("elapsed_s", 0.0)
        )

    raw_plan = raw_plan_content

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

    # ----- validate + clean -----
    revised_plan, plan_warnings = _validate_and_clean_plan(revised_plan)
    for w in plan_warnings:
        console.print(f"[yellow]plan: {escape(w)}[/yellow]")

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
        whitelist = list(task.tools) if task.tools else None
        if whitelist is not None:
            # These read-only tools are always needed: navigation, verification, content search
            for always in ("read_file", "list_dir", "search_file", "write_file"):
                if always not in whitelist:
                    whitelist.append(always)
        # keep_alive="1m" releases VRAM 1 min after each executor finishes,
        # preventing accumulation across heavy tasks (e.g. large write_file).
        executor = SubAgent(
            model=model, system_prompt=EXECUTOR_SYS,
            tools_whitelist=whitelist,
            num_ctx=16384, label=f"executor {idx}/{total} (id={task.id})",
            max_tool_calls=15, keep_alive="1m",
        )
        user_msg = _build_executor_user_msg(task, goal, done_so_far,
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
                # ok but no SUMMARY/FAILED marker. If this task was supposed to
                # write/patch a file but nothing was actually touched, the tool
                # call never executed (e.g. a parse failure) — do NOT report it
                # as done just because the model emitted some final text.
                wants_write = any(t in ("write_file", "patch_file")
                                  for t in (task.tools or []))
                if wants_write and not result["files_touched"]:
                    task.status = "failed"
                    task.summary = ("no file was written/patched — the tool call "
                                    "produced no file (likely failed to parse)")
                else:
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
    verifier_msg = (f"Plan with checkboxes after execution:\n\n{final_plan}\n\n"
                 f"Files touched by executors:\n{files_msg}\n\n"
                 "Verify now. End with the JSON verdict block.")
    verifier_result = verifier.run(verifier_msg)
    if session_log:
        session_log.log_step(
            kind="assistant",
            content=f"[plan - verifier subagent]: {verifier_result.get('content', '')}",
            prompt_tokens=verifier_result.get("tokens", {}).get("prompt", 0),
            gen_tokens=verifier_result.get("tokens", {}).get("gen", 0),
            elapsed_s=verifier_result.get("elapsed_s", 0.0)
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

    # ----- parse verifier verdict -----
    verdict_data = None
    raw_verdict = verifier_result.get("content", "")
    json_match = re.search(r"```json\s*(.*?)\s*```", raw_verdict, re.DOTALL)
    if json_match:
        try:
            verdict_data = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    if verdict_data:
        verdict          = verdict_data.get("verdict", "unknown")
        confirmed_ids    = set(verdict_data.get("confirmed", []))
        rejected_list    = verdict_data.get("rejected", [])
        verdict_summary  = verdict_data.get("summary", "")
        verdict_color    = {"ok": "green", "incomplete": "yellow", "broken": "red"}.get(verdict, "white")

        verdict_table = Table(title="🔍 verifier", border_style="magenta", show_header=True)
        verdict_table.add_column("id", justify="right", style="dim")
        verdict_table.add_column("result")
        verdict_table.add_column("detail", style="dim")
        for tid in sorted(confirmed_ids):
            verdict_table.add_row(str(tid), "[green]confirmed[/green]", "")
        for entry in rejected_list:
            verdict_table.add_row(str(entry.get("id", "?")),
                                  "[red]rejected[/red]",
                                  entry.get("reason", "")[:80])
        console.print(verdict_table)
        console.print(Panel(
            f"verdict: [{verdict_color}]{verdict}[/{verdict_color}]\n\n{escape(verdict_summary[:600])}",
            title="🔍 verifier verdict", border_style=verdict_color))
    elif raw_verdict:
        console.print(Panel(raw_verdict[:3000], title="🔍 verifier", border_style="magenta"))

    done = sum(1 for t in ordered if t.status == "done")
    failed = sum(1 for t in ordered if t.status == "failed")
    skipped = sum(1 for t in ordered if t.status == "skipped")
    confirmed_count = len(verdict_data.get("confirmed", [])) if verdict_data else 0
    rejected_count  = len(verdict_data.get("rejected",  [])) if verdict_data else 0

    result_color = "green" if failed == 0 and (not verdict_data or verdict == "ok") else \
                   "red"   if verdict_data and verdict == "broken" else "yellow"
    console.print(Panel(
        f"✓ done: [green]{done}[/green]  ✗ failed: [red]{failed}[/red]  "
        f"⊘ skipped: [yellow]{skipped}[/yellow]  / {total}\n"
        f"verifier: [green]{confirmed_count} confirmed[/green]  [red]{rejected_count} rejected[/red]\n"
        f"executors elapsed: {exec_elapsed:.1f}s\n"
        f"plan file: {plan_path}",
        title="result", border_style=result_color))

    # Inject into main conversation so the main agent is aware
    history = ctx.get("conversation_history")
    if history is not None:
        history.append({
            "role": "user",
            "content": (f"[PLAN COMPLETED]\n"
                        f"Plan file: plans/{plan_path.name}\n"
                        f"Done: {done}/{total}. Failed: {failed}. Skipped: {skipped}.\n"
                        f"Verifier said:\n{verifier_result['content'][:2000]}"),
        })

    return {"status": "ok", "done": done, "failed": failed,
            "skipped": skipped, "plan_path": str(plan_path)}
