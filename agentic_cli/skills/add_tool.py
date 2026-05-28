"""Meta-skill: scaffold a new tool function.

The new tool is appended to a `extra_tools.py` file (created if needed)
and registered in CORE_TOOLS via a small import-time hook on next run.
For the first iteration we only generate the file and instruct the user
to add it to tools.CORE_TOOLS manually if they want it auto-loaded; the
agent can still call it once we wire dispatch (done in agent.py).
"""

import re
import ollama
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markup import escape

NAME = "add_tool"
DESCRIPTION = "Generate a new tool function from a description"

console = Console()


TEMPLATE_PROMPT = """Write a new tool function for the agentic_cli project.

Tool format (Python):

    def <tool_name>(args):
        '''Short description.'''
        # args is a dict with parameters
        try:
            ...
            return {{"result": ...}}
        except Exception as e:
            return {{"error": str(e)}}

Conventions:
- Use _err(msg, hint) idiom if you import from tools.
- Return a dict. Errors as {{"error": "...", "hint": "..."}}.
- Validate required args at the top.

User's description of the new tool:
{description}

Output ONLY Python source, no markdown fences. Include any imports at
the top of the file."""


def run(args, ctx):
    description = (args or "").strip()
    if not description:
        return {"error": "usage: /skill add_tool <describe the new tool>"}

    try:
        resp = ollama.chat(
            model=ctx["model"],
            messages=[{"role": "user", "content": TEMPLATE_PROMPT.format(description=description)}],
            stream=False,
        )
        code = (resp.get("message", {}).get("content")
                if isinstance(resp, dict) else resp.message.content) or ""
    except Exception as e:
        return {"error": f"generation failed: {e}"}

    code = re.sub(r"^```(?:python)?\s*", "", code.strip())
    code = re.sub(r"\s*```$", "", code).strip()

    target = Path(ctx["working_dir"]) / "extra_tools.py"
    header = "" if target.exists() else (
        "\"\"\"User-generated extra tools. Auto-loaded by agentic_cli.\"\"\"\n\n")
    with open(target, "a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write("\n\n# --- added by /skill add_tool ---\n")
        f.write(code + "\n")

    # Detect the function name
    fn_match = re.search(r"def\s+(\w+)\s*\(", code)
    tool_name = fn_match.group(1) if fn_match else "?"

    console.print(Panel(
        f"[green]appended[/green] tool [bold]{tool_name}[/bold] to extra_tools.py\n"
        f"it will be available to the agent on the next prompt.",
        title="add_tool", border_style="green"))
    return {"status": "ok", "tool_name": tool_name, "path": str(target)}
