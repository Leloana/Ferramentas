"""WINCLI — the agent cli, windows native.

Black & white interface. Every choice is made with the arrow keys + Enter
(see ui.select); nothing in the UI requires typing a letter to pick an
option. The chat opens straight into the last model you used (remembered in
~/.wincli_config.json); switch models any time with /models.

Slash commands:
  /models                → switch model (arrow-key menu); remembered for next run
  /init                  → regenerate WINCLI.md
  /mode [args]           → show or change op/perm mode
  /context               → session dashboard
  /clear                 → wipe conversation history (keeps session log, frees VRAM)
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
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.history import FileHistory

from agent import run_agent_loop
from modes import SessionState, handle_mode_command
from persist import SessionLog, list_sessions, load_session, rebuild_history
from snapshot import SnapshotManager
import skills as skills_pkg
import tools
import ui
from ui import console

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
    wd = str(working_dir).replace("\\", "/")
    wincli_rule = "\n8. WINCLI.md is loaded above — follow it." if wincli_content else ""
    return f"""You are WINCLI, an agentic coding assistant on Windows.
You act ONLY by calling tools. You cannot edit files or run anything except
through the tools listed below.

WORKING DIRECTORY: {wd}

PATHS — follow exactly:
- Every path MUST be absolute.
- ALWAYS write paths with forward slashes "/", NEVER backslashes.
    Correct:  "{wd}/src/app.py"
    Wrong:    "{wd}\\src\\app.py"   ← backslashes break the JSON
- Never use "./", "../", or a bare filename.
{wincli_section}
TOOLS — this is the COMPLETE list. Never invent another tool name or argument key.
- read_file    {{"path": "<abs>"}}                      → returns lines WITH line numbers
- list_dir     {{"path": "<abs dir>"}}
- search_file  {{"path": "<abs>", "query": "<text>"}}
- write_file   {{"path": "<abs>", "content": "<full file text>"}}  → creates/overwrites the WHOLE file
- append_file  {{"path": "<abs>", "content": "<text>"}}   → adds text to the END (creates if missing)
- patch_file   {{"path": "<abs>", "start_line": <int>, "end_line": <int>, "new_content": "<text>"}}
                 → replaces lines start_line..end_line (inclusive). Get the numbers from read_file FIRST.
- remove_file  {{"path": "<abs>", "recursive": true|false}}   → needs user confirmation
- run_command  {{"command": "<powershell>"}}   ⚠ NON-BLOCKING: returns a PID only, NEVER the output
- http_get     {{"url": "<url>"}}

RESPONSE FORMAT — every reply is EXACTLY ONE of these, never both:

  FORM A (use a tool): output ONE ```json block and NOTHING else — no text around it.
    ```json
    {{"tool": "read_file", "args": {{"path": "{wd}/main.py"}}}}
    ```

  FORM B (talk to the user): plain text only, with NO ```json block anywhere.
    Use FORM B to ask a question or to give the final answer.

WORKED EXAMPLE — note: one tool per reply, read before patch, then stop.
  user: add an import to main.py
  you:  ```json
        {{"tool": "read_file", "args": {{"path": "{wd}/main.py"}}}}
        ```
  result: (file shown with line numbers)
  you:  ```json
        {{"tool": "patch_file", "args": {{"path": "{wd}/main.py", "start_line": 3, "end_line": 3, "new_content": "import logging"}}}}
        ```
  result: Patched {wd}/main.py
  you:  Added the logging import to main.py.

RULES:
1. ONE tool call per reply. Then STOP and wait for the result before the next.
2. Never repeat a tool call with identical args. If it failed, change the args or switch to FORM B and explain.
3. New file → write_file. Editing part of an existing file → read_file first, then patch_file with the line numbers you saw. A LARGE new file → write_file the first section, then append_file the rest in chunks (one small call each) — never write_file the same path twice (it overwrites).
4. run_command is PowerShell (`Get-ChildItem`, not `ls`) and NON-BLOCKING. To check a result, read_file/search_file the output file — you will NOT get run_command's stdout.
5. PRE-CHECK: before write_file / patch_file / remove_file, make sure you've seen the file THIS turn — either read_file it (best when editing) or list_dir its parent directory.
6. Thinking goes inside <think>...</think>. Never put a tool call inside <think>.
7. When the task is done, reply in FORM B with one short line (created/modified/ran). Do NOT keep calling tools after it is done.{wincli_rule}

REMEMBER: one ```json tool call per turn · absolute paths with forward slashes · nothing outside the fence."""


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
    sub = session_log.subagent_totals()
    if sub["prompt_tokens"] or sub["gen_tokens"]:
        table.add_row("subagent tokens (Σ)",
                      f"{sub['prompt_tokens'] + sub['gen_tokens']:,} "
                      f"(plan/skills, not in prompt counter)")
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
            console.print("no sessions found in .persist/")
            return None, None
        options = []
        for s in sessions:
            label = (f"{s['id']}  ·  {s['model']}  ·  {s['turns']} turns  ·  "
                     f"{s['started_at'][:19]}")
            options.append((label, s))
        options.append(("cancel", None))
        chosen = ui.select(options, title="resume which session?")
        if chosen is None:
            return None, None
        data = load_session(working_dir, chosen["id"])
        return data, chosen["model"]

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


def fetch_models():
    """Return the list of available ollama model names, or exit on failure."""
    with console.status("connecting to ollama...", spinner="line"):
        try:
            models_data = ollama.list()
        except Exception as e:
            ui.panel(f"ollama not reachable: {escape(str(e))}", title="error")
            ui.reset_background()
            sys.exit(1)
    available = [m.get("name", m.get("model", "")) for m in models_data.get("models", [])]
    available = [n for n in available if n]
    if not available:
        console.print("no models found. run `ollama pull <model>` first.")
        ui.reset_background()
        sys.exit(1)
    return available


def choose_model(available, *, current=None, force_menu=False):
    """Pick a model via the arrow-key menu, remembering the choice.

    If a remembered/last model is still available and force_menu is False, it
    is used directly (the chat opens straight into it). Returns the model name.
    """
    last = current or ui.get_last_model()
    if not force_menu and last in available:
        return last

    default = available.index(last) if last in available else 0
    chosen = ui.select(
        [(m, m) for m in available],
        title="select model  (change later with /models)",
        default=default,
    )
    if chosen is None:
        # On first-run cancel we must still have a model.
        chosen = last if last in available else available[0]
    ui.set_last_model(chosen)
    return chosen


def main():
    ui.paint_background()
    ui.header()

    working_dir = Path.cwd().resolve()
    console.print(f"  working dir: {working_dir}", style="dim")

    available = fetch_models()
    # Opens straight into the last chosen model (config memory); only shows the
    # arrow-key menu on first run or when the remembered model is gone.
    model = choose_model(available)

    wincli_content, wincli_loaded = load_wincli_context(working_dir)
    state = SessionState()
    session_log = SessionLog(working_dir, model)
    snapshot_mgr = SnapshotManager(working_dir, session_log.session_id)

    ui.panel(
        f"model: {model}\n"
        f"WINCLI.md: {'loaded' if wincli_loaded else 'not found — run /init'}\n"
        f"persist: {session_log.path}\n"
        f"mode: {state.mode_label()}  (change via /mode)\n"
        f"skills: {len(skills_pkg.index())} discovered  (list via /skills)\n"
        "commands: /models /init /mode /focus /context /clear /skills /skill /plan "
        "/debug /reflect /resume /undo  exit",
        title="ready")

    system_prompt = build_system_prompt(working_dir, wincli_content)
    tools.set_working_dir(working_dir)
    conversation_history = [{"role": "system", "content": system_prompt}]
    history = FileHistory(str(working_dir / ".persist" / ".history"))

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
            console.print("\ngoodbye!", style="dim")
            tools.cleanup_background_processes()
            ui.reset_background()
            sys.exit(0)

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            console.print("goodbye!", style="dim")
            tools.cleanup_background_processes()
            ui.reset_background()
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

            if cmd in ("models", "model"):
                available = fetch_models()
                new_model = choose_model(available, current=model, force_menu=True)
                if new_model and new_model != model:
                    model = new_model
                    conversation_history[0] = {
                        "role": "system",
                        "content": build_system_prompt(working_dir, wincli_content),
                    }
                    console.print(f"model → {model}", style="bold")
                else:
                    console.print("model unchanged", style="dim")
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

            if cmd == "clear":
                kept = len(conversation_history) - 1  # everything except system prompt
                conversation_history.clear()
                conversation_history.append({"role": "system",
                                             "content": build_system_prompt(working_dir,
                                                                             wincli_content)})
                console.print(f"[green]context cleared[/green] [dim]({kept} messages removed — "
                              f"model memory reset, session log preserved)[/dim]")
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
