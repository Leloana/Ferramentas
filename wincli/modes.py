"""Mode & permission state for the session.

Two orthogonal axes:

- op_mode      : "normal" | "plan" | "debug"   (how prompts are processed)
- perm_mode    : "bypass" | "ask_edits" | "ask_all"  (how tools are gated)

A SessionPermissions object also tracks per-tool/per-path "always allow"
grants so the user only has to confirm each kind of action once per
session.
"""

from dataclasses import dataclass, field
from typing import Set, Dict
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt
from pathlib2 import Path

console = Console()


# Tools that modify state (anything that isn't pure read).
MUTATING_TOOLS = {"write_file", "patch_file", "run_command"}


@dataclass
class SessionState:
    op_mode: str = "normal"          # normal | plan | debug
    perm_mode: str = "ask_edits"     # bypass | ask_edits | ask_all
    focus: bool = False              # focus mode: hide non-essential UI
    always_allow_tools: Set[str] = field(default_factory=set)
    always_allow_paths: Dict[str, Set[str]] = field(default_factory=dict)

    def mode_label(self):
        f = "/focus" if self.focus else ""
        return f"{self.op_mode}/{self.perm_mode}{f}"


def _needs_gate(state: SessionState, tool_name: str) -> bool:
    if state.perm_mode == "bypass":
        return False
    if state.perm_mode == "ask_all":
        return True
    # ask_edits: only gate mutating tools
    return tool_name in MUTATING_TOOLS


def _diff_preview(tool_name, args):
    """Render a preview of what the tool is about to do."""
    if tool_name == "write_file":
        path = args.get("path", "?")
        content = args.get("content", "")
        existing = ""
        try:
            p = Path(path)
            if p.exists():
                existing = p.read_text(encoding="utf-8")
        except Exception:
            pass
        if existing:
            import difflib
            diff = "".join(difflib.unified_diff(
                existing.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=path, tofile=path, n=2,
            ))
            if diff:
                return Syntax(diff[:4000], "diff", theme="ansi_dark", line_numbers=False)
        # New file
        return Panel(
            Syntax(content[:2000], "python", theme="ansi_dark"),
            title=f"NEW FILE: {path}", border_style="green")

    if tool_name == "patch_file":
        path = args.get("path", "?")
        info = []
        if "start_line" in args:
            info.append(f"lines {args.get('start_line')}-{args.get('end_line')}")
        if "old_str" in args:
            info.append(f"old_str:\n{(args.get('old_str') or '')[:400]}")
        if "new_str" in args:
            info.append(f"new_str:\n{(args.get('new_str') or '')[:400]}")
        if "new_content" in args:
            info.append(f"new_content:\n{(args.get('new_content') or '')[:400]}")
        return Panel("\n\n".join(info), title=f"PATCH: {path}", border_style="yellow")

    if tool_name == "run_command":
        cmd = args.get("command", "")
        try:
            body = Syntax(cmd, "powershell", theme="ansi_dark",
                          word_wrap=True, line_numbers=False)
        except Exception:
            body = cmd
        from tools import _WORKING_DIR
        wd = str(_WORKING_DIR) if _WORKING_DIR is not None else str(Path.cwd())
        return Panel(body, title=f"POWERSHELL  [dim]({wd})[/dim]",
                     border_style="red")

    return Panel(str(args)[:1000], title=tool_name, border_style="blue")


def gate_tool(state: SessionState, tool_name: str, args: dict):
    """Returns True if the tool may execute. May mutate `state` to remember
    'always allow' grants."""
    if not _needs_gate(state, tool_name):
        return True
    if tool_name in state.always_allow_tools:
        return True
    path_key = args.get("path")
    if path_key and path_key in state.always_allow_paths.get(tool_name, set()):
        return True

    console.print(_diff_preview(tool_name, args))
    legend = "[green]y[/green]=yes  [red]n[/red]=no  [cyan]a[/cyan]=always this tool"
    if path_key:
        legend += "  [cyan]p[/cyan]=always this path"
    console.print(f"[dim]{legend}[/dim]")
    choice = Prompt.ask(
        f"[yellow]Allow [bold]{tool_name}[/bold]"
        + (f" on [bold]{path_key}[/bold]" if path_key else "")
        + "?[/yellow]",
        choices=["y", "n", "a", "p"] if path_key else ["y", "n", "a"],
        default="n",
    ).lower()
    if choice == "n":
        return False
    if choice == "a":
        state.always_allow_tools.add(tool_name)
        return True
    if choice == "p" and path_key:
        state.always_allow_paths.setdefault(tool_name, set()).add(path_key)
        return True
    return True  # 'y'


def handle_mode_command(state: SessionState, args: str):
    """Implements the /mode slash command.

    Usage:
      /mode                       → show current
      /mode bypass | ask_edits | ask_all
      /mode op normal | plan | debug
    """
    args = (args or "").strip()
    if not args:
        console.print(Panel(
            f"op_mode  = [bold cyan]{state.op_mode}[/bold cyan]\n"
            f"perm_mode= [bold cyan]{state.perm_mode}[/bold cyan]\n"
            f"always-allow tools: {sorted(state.always_allow_tools) or '—'}\n"
            f"always-allow paths: {dict(state.always_allow_paths) or '—'}\n\n"
            "[dim]/mode bypass | ask_edits | ask_all[/dim]\n"
            "[dim]/mode op normal | plan | debug[/dim]",
            title="Mode", border_style="cyan"))
        return

    parts = args.split()
    if parts[0] == "op" and len(parts) >= 2:
        new = parts[1]
        if new in ("normal", "plan", "debug"):
            state.op_mode = new
            console.print(f"[green]op_mode → {new}[/green]")
        else:
            console.print(f"[red]invalid op_mode: {new}[/red]")
        return

    if parts[0] in ("bypass", "ask_edits", "ask_all"):
        state.perm_mode = parts[0]
        console.print(f"[green]perm_mode → {parts[0]}[/green]")
        return

    console.print(f"[red]unknown mode argument: {args}[/red]")
