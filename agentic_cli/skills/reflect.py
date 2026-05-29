"""Reflection skill.

Triggered manually via /skill reflect OR automatically by the circuit
breaker when the agent fails the same tool 3 times. It asks a clean
sub-prompt (no tool calls) to look back at the last N messages and
propose a different approach.
"""

import time
import ollama
from rich.panel import Panel
from rich.markup import escape

NAME = "reflect"
DESCRIPTION = "Step back, analyze stuck state, propose a different approach"

from ui import console


REFLECT_SYSTEM = """You are a debugging coach. You will be given the recent
conversation between an AI agent and a user. The agent got stuck. Your job:

1. State in one sentence what the agent was trying to do.
2. State what went wrong (be specific — quote tool errors).
3. Propose ONE different approach the agent should try next. Be concrete:
   which tool, with which arguments, in which order.

Do not call tools yourself. Output plain text under ~200 words.
"""


def run(args, ctx):
    history = ctx.get("conversation_history") or []
    # Take the last 12 messages, excluding the system prompt
    recent = [m for m in history if m.get("role") != "system"][-12:]
    transcript = "\n\n".join(
        f"[{m.get('role')}]: {m.get('content','')[:1500]}" for m in recent)

    user_msg = f"Recent transcript:\n\n{transcript}\n\nUser hint (optional): {args or 'none'}"

    try:
        start = time.time()
        resp = ollama.chat(
            model=ctx["model"],
            messages=[
                {"role": "system", "content": REFLECT_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            stream=False,
        )
        reasoning = ""
        if isinstance(resp, dict):
            msg = resp.get("message", {})
            content = msg.get("content", "") or ""
            reasoning = msg.get("reasoning_content", "") or ""
            prompt_tokens = resp.get("prompt_eval_count", 0) or 0
            gen_tokens = resp.get("eval_count", 0) or 0
        else:
            msg = getattr(resp, "message", None)
            content = getattr(msg, "content", "") if msg else ""
            reasoning = getattr(msg, "reasoning_content", "") if msg and hasattr(msg, "reasoning_content") else ""
            prompt_tokens = getattr(resp, "prompt_eval_count", 0) or 0
            gen_tokens = getattr(resp, "eval_count", 0) or 0

        if reasoning:
            content = f"<think>{reasoning}</think>\n{content}"

        elapsed = time.time() - start
        from agent import strip_think_blocks
        content = strip_think_blocks(content)

        session_log = ctx.get("session_log")
        if session_log:
            session_log.log_step(
                kind="assistant",
                content=f"[reflect]: {content.strip()}",
                prompt_tokens=prompt_tokens,
                gen_tokens=gen_tokens,
                elapsed_s=elapsed
            )
    except Exception as e:
        return {"error": f"reflect failed: {e}"}

    console.print(Panel(content.strip(), title="Reflection", border_style="magenta"))

    # Inject the reflection as a system note so the agent's next turn uses it.
    if history is not None:
        history.append({
            "role": "user",
            "content": f"[REFLECTION]\n{content.strip()}\n\nApply this approach now.",
        })
    return {"status": "ok", "elapsed_s": elapsed}
