"""Meta-skill: scaffold a new skill from a natural-language description.

Asks the LLM to fill the standard skill template, writes the file to
skills/<slug>.py, and invalidates the skill index so it's picked up on
next use.
"""

import re
import time
import ollama
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markup import escape

NAME = "add_skill"
DESCRIPTION = "Generate a new skill file from a description"

console = Console()


TEMPLATE_PROMPT = """Write a new skill file for the agentic_cli project.

Skill format (Python):

    NAME = "<short_snake_name>"
    DESCRIPTION = "<one-line description>"

    def run(args, ctx):
        # args: str passed after /skill <name>
        # ctx keys: working_dir, model, wincli_content,
        #          conversation_history, session_log, state
        ...
        return {{"status": "ok"}}

Conventions:
- Use ollama.chat for LLM calls if needed.
- Use ctx['conversation_history'].append({{role,content}}) to inject
  instructions into the next agent turn.
- Return a dict; on error return {{"error": "..."}}.

User's description of the new skill:
{description}

Output ONLY the Python source code, no markdown fences."""


def _slug(text):
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[-\s]+", "_", s).strip("_")
    return (s or "skill")[:40]


def run(args, ctx):
    description = (args or "").strip()
    if not description:
        return {"error": "usage: /skill add_skill <describe the new skill>"}

    try:
        start = time.time()
        resp = ollama.chat(
            model=ctx["model"],
            messages=[{"role": "user", "content": TEMPLATE_PROMPT.format(description=description)}],
            stream=False,
        )
        if isinstance(resp, dict):
            prompt_tokens = resp.get("prompt_eval_count", 0) or 0
            gen_tokens = resp.get("eval_count", 0) or 0
        else:
            prompt_tokens = getattr(resp, "prompt_eval_count", 0) or 0
            gen_tokens = getattr(resp, "eval_count", 0) or 0

        elapsed = time.time() - start
        code = (resp.get("message", {}).get("content")
                if isinstance(resp, dict) else resp.message.content) or ""
        from agent import strip_think_blocks
        code = strip_think_blocks(code)
    except Exception as e:
        return {"error": f"generation failed: {e}"}

    # Strip accidental code fences
    code = re.sub(r"^```(?:python)?\s*", "", code.strip())
    code = re.sub(r"\s*```$", "", code).strip()

    # Try to detect NAME from the generated code, fall back to slug
    name_match = re.search(r'NAME\s*=\s*[\'"]([^\'"]+)[\'"]', code)
    name = name_match.group(1) if name_match else _slug(description)

    skills_dir = Path(__file__).parent
    target = skills_dir / f"{name}.py"
    if target.exists():
        return {"error": f"skill file already exists: {target.name}"}

    target.write_text(code + "\n", encoding="utf-8")

    # Invalidate index so the new skill is discovered
    import skills as skills_pkg
    skills_pkg.invalidate()

    session_log = ctx.get("session_log")
    if session_log:
        session_log.log_step(
            kind="assistant",
            content=f"[add_skill]: {name}",
            prompt_tokens=prompt_tokens,
            gen_tokens=gen_tokens,
            elapsed_s=elapsed
        )

    console.print(Panel(
        f"[green]created[/green] skills/{target.name}\n"
        f"invoke with: /skill {name} <args>",
        title="add_skill", border_style="green"))
    return {"status": "ok", "name": name, "path": str(target)}
