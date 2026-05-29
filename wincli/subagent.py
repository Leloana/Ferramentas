"""Isolated sub-agent for multi-agent flows.

A SubAgent is a stripped-down version of run_agent_loop:
  - Independent conversation (no shared history)
  - Tools restricted to a whitelist
  - Configurable num_ctx + keep_alive
  - Rich real-time streaming display (spinner, tokens, t/s, tail)
  - Returns a structured result with token/time stats and files touched

Used by the multi-agent plan flow (planner / reviewer / executor / verifier).
"""

import hashlib
import json
import queue
import re
import threading
import time
from typing import Optional, List, Dict, Any

import ollama
from rich.live import Live
from rich.markup import escape
from rich.text import Text

import tools as tools_mod
from agent import parse_tool_call, format_tool_result, _strip_thinking, _dispatch_tool, strip_think_blocks
import ui
from ui import console

THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

# Spinners
_THINK_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_TOOL_SPIN  = "◐◓◑◒"
_IDLE_SPIN  = "⡏⡟⡯⣏"

# Detect partial tool name in streaming buffer
_TOOL_NAME_RE = re.compile(r'"tool"\s*:\s*"(\w+)"')
_PATH_RE      = re.compile(r'"(?:path|url)"\s*:\s*"([^"]+)"')


def _detect_tool_mid_stream(text: str):
    """Return (tool_name, path) if a partial tool JSON is visible."""
    m = _TOOL_NAME_RE.search(text)
    if not m:
        return None, None
    name = m.group(1)
    pm = _PATH_RE.search(text)
    path = pm.group(1) if pm else None
    return name, path


def _wrap_tail(text: str, width: int = 100) -> str:
    """Last `width` chars of text, replacing newlines, word-bounded."""
    if not text:
        return ""
    flat = text.replace("\n", " ⏎ ")
    if len(flat) <= width:
        return flat
    snip = flat[-width:]
    sp = snip.find(" ")
    if 0 < sp < 20:
        snip = snip[sp + 1:]
    return "…" + snip


class SubAgent:
    """An isolated agent with its own context and tool whitelist."""

    def __init__(self, *, model: str, system_prompt: str,
                 tools_whitelist: Optional[List[str]] = None,
                 num_ctx: int = 16384, keep_alive: str = "10m",
                 max_tool_calls: int = 15, max_strikes: int = 3,
                 label: str = "subagent", temperature: float = 0.2):
        self.model = model
        self.system_prompt = system_prompt
        self.whitelist = set(tools_whitelist) if tools_whitelist is not None else None
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.max_tool_calls = max_tool_calls
        self.max_strikes = max_strikes
        self.label = label
        self.temperature = temperature

    # ------------------------------------------------------------------ helpers

    def _args_hash(self, tool_name, args):
        try:
            s = json.dumps(args, sort_keys=True, ensure_ascii=False)
        except Exception:
            s = str(args)
        return hashlib.md5(f"{tool_name}|{s}".encode("utf-8")).hexdigest()[:10]

    def _gate_tool(self, tool_name: str) -> bool:
        if self.whitelist is None:
            return True
        return tool_name in self.whitelist

    # ------------------------------------------------------------------ streaming

    def _stream_response(self, messages: list, live: Live, step: int,
                         tool_call_count: int) -> dict:
        """Stream one model response, updating `live` every chunk.

        Returns:
            {
              "content": str,          # full raw content (with <think> tags)
              "prompt_tokens": int,
              "gen_tokens": int,
              "elapsed_s": float,
            }
        """
        q: queue.Queue = queue.Queue()

        def _worker():
            try:
                escaped = []
                for m in messages:
                    if m["role"] == "user":
                        escaped.append({"role": "user",
                                        "content": m["content"].replace("\\", "\\\\")})
                    else:
                        escaped.append(m)
                stream = ollama.chat(
                    model=self.model,
                    messages=escaped,
                    stream=True,
                    keep_alive=self.keep_alive,
                    options={"num_ctx": self.num_ctx, "temperature": self.temperature},
                )
                for chunk in stream:
                    q.put(("chunk", chunk))
                q.put(("done", None))
            except Exception as e:
                q.put(("error", e))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

        parts: List[str] = []
        token_count = 0
        tick = 0
        start = time.time()
        final_prompt = 0
        final_gen = 0
        in_reasoning = False

        while True:
            # Drain all pending chunks
            drained = False
            while True:
                try:
                    kind, val = q.get_nowait()
                except queue.Empty:
                    break
                drained = True
                if kind == "error":
                    raise val
                if kind == "done":
                    if in_reasoning:
                        parts.append("</think>\n")
                    # collect final token counts
                    return {
                        "content": "".join(parts),
                        "prompt_tokens": final_prompt,
                        "gen_tokens": final_gen or token_count,
                        "elapsed_s": time.time() - start,
                    }
                # kind == "chunk"
                chunk = val
                if isinstance(chunk, dict):
                    msg = chunk.get("message", {})
                    content_tok = msg.get("content", "") or ""
                    reasoning   = msg.get("reasoning_content", "") or ""
                    if chunk.get("done"):
                        final_prompt = chunk.get("prompt_eval_count", 0) or 0
                        final_gen    = chunk.get("eval_count", 0) or 0
                else:
                    msg = getattr(chunk, "message", None)
                    content_tok = getattr(msg, "content", "") if msg else ""
                    reasoning   = getattr(msg, "reasoning_content", "") if msg and hasattr(msg, "reasoning_content") else ""
                    if getattr(chunk, "done", False):
                        final_prompt = getattr(chunk, "prompt_eval_count", 0) or 0
                        final_gen    = getattr(chunk, "eval_count", 0) or 0

                token_parts = []
                if reasoning:
                    if not in_reasoning:
                        token_parts.append("<think>")
                        in_reasoning = True
                    token_parts.append(reasoning)
                elif content_tok:
                    if in_reasoning:
                        token_parts.append("</think>\n")
                        in_reasoning = False
                    token_parts.append(content_tok)

                tok = "".join(token_parts)
                if tok:
                    parts.append(tok)
                    token_count += 1

            # Update display every iteration (even when no new chunks — tick still advances)
            elapsed = time.time() - start
            tps = token_count / elapsed if elapsed > 0 else 0
            acc = "".join(parts)
            detected_tool, detected_path = _detect_tool_mid_stream(acc)

            live.update(self._render_streaming(
                step=step,
                tool_call_count=tool_call_count,
                token_count=token_count,
                elapsed=elapsed,
                tps=tps,
                detected_tool=detected_tool,
                detected_path=detected_path,
                tail=acc,
                tick=tick,
                in_reasoning=in_reasoning,
            ))
            tick += 1
            time.sleep(0.08)

    # ------------------------------------------------------------------ render

    def _render_streaming(self, *, step: int, tool_call_count: int,
                          token_count: int, elapsed: float, tps: float,
                          detected_tool: Optional[str], detected_path: Optional[str],
                          tail: str, tick: int, in_reasoning: bool) -> Text:
        t = Text()

        # Header line: label + call counter
        t.append_text(Text.from_markup(
            f"  [bold cyan]{escape(self.label)}[/bold cyan]"
            f"  [dim]step {step} | {tool_call_count} tool calls[/dim]\n"
        ))

        # Phase line
        if detected_tool:
            sp = _TOOL_SPIN[tick % len(_TOOL_SPIN)]
            path_hint = f" [dim]→ {escape(detected_path[:60])}[/dim]" if detected_path else ""
            t.append_text(Text.from_markup(
                f"  [cyan]{sp}[/cyan] calling [yellow]{escape(detected_tool)}[/yellow]{path_hint}\n"
            ))
        elif token_count == 0:
            sp = _IDLE_SPIN[tick % len(_IDLE_SPIN)]
            t.append_text(Text.from_markup(
                f"  [dim]{sp} waiting for first token...[/dim]\n"
            ))
        elif in_reasoning:
            sp = _THINK_SPIN[tick % len(_THINK_SPIN)]
            t.append_text(Text.from_markup(
                f"  [magenta]{sp}[/magenta] [magenta]thinking[/magenta]\n"
            ))
        else:
            sp = _THINK_SPIN[tick % len(_THINK_SPIN)]
            t.append_text(Text.from_markup(
                f"  [blue]{sp}[/blue] [blue]generating[/blue]\n"
            ))

        # Stats line
        t.append_text(Text.from_markup(
            f"  [dim]⚡ {tps:.1f} t/s | {token_count} tokens | {elapsed:.1f}s[/dim]\n"
        ))

        # Content tail
        visible_tail = _wrap_tail(strip_think_blocks(tail))
        if visible_tail:
            t.append_text(Text.from_markup(
                f"  [dim]{escape(visible_tail[:120])}[/dim]"
            ))
        return t

    def _render_idle(self, phase: str, step: int) -> Text:
        """Used between streaming calls (tool execution phase)."""
        sp = _IDLE_SPIN[step % len(_IDLE_SPIN)]
        return Text.from_markup(
            f"  [cyan]{sp}[/cyan] [bold]{escape(self.label)}[/bold]: {escape(phase)}"
        )

    # ------------------------------------------------------------------ main loop

    def run(self, user_message: str) -> Dict[str, Any]:
        """Run the subagent until it stops calling tools or hits limits.

        Returns:
            {
              "status": "ok" | "stuck" | "max_calls" | "error",
              "content": str,           # final visible answer
              "thinking": str,          # all <think> blocks concatenated
              "tool_calls": [...],      # list of executed calls
              "files_touched": [str],   # paths from write/patch tools
              "tokens": {"prompt": int, "gen": int},
              "elapsed_s": float,
              "strikes_tripped": bool,
            }
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": user_message},
        ]
        tool_calls_log: List[Dict[str, Any]] = []
        files_touched:  List[str] = []
        consecutive_failures: Dict[str, int] = {}
        prompt_total = 0
        gen_total    = 0
        start        = time.time()
        status       = "ok"
        strikes_tripped = False
        final_content   = ""
        thinking_accum: List[str] = []

        with Live(self._render_idle("starting…", 0),
                  refresh_per_second=12, console=console) as live:

            for step in range(self.max_tool_calls + 1):
                # ---- stream one model response ----
                live.update(self._render_idle("connecting…", step))
                try:
                    resp = self._stream_response(messages, live, step,
                                                 len(tool_calls_log))
                except Exception as e:
                    status = "error"
                    final_content = f"model call failed: {e}"
                    break

                content = resp["content"]
                prompt_total += resp["prompt_tokens"]
                gen_total    += resp["gen_tokens"]

                thoughts, visible = _strip_thinking(content)
                if thoughts:
                    thinking_accum.append(thoughts)

                tool_call = parse_tool_call(visible)

                # ---- no tool call → final answer ----
                if not (tool_call and isinstance(tool_call, dict) and "tool" in tool_call):
                    final_content = visible
                    break

                tool_name = tool_call.get("tool")
                tool_args = tool_call.get("args", {}) or {}

                # ---- whitelist check ----
                live.update(self._render_idle(f"executing {tool_name}…", step))
                if not self._gate_tool(tool_name):
                    result  = {"error": f"tool '{tool_name}' not in whitelist",
                               "hint": f"allowed: {sorted(self.whitelist) if self.whitelist else 'all'}"}
                    success = False
                else:
                    result  = self._execute(tool_name, tool_args)
                    success = "error" not in result and result.get("returncode", 0) in (0, None)

                tool_calls_log.append({"name": tool_name, "args": tool_args,
                                       "result": result, "success": success})

                # ---- log file writes immediately ----
                if success and tool_name in ("write_file", "patch_file"):
                    p = tool_args.get("path")
                    if p:
                        if p not in files_touched:
                            files_touched.append(p)
                        verb = "wrote" if tool_name == "write_file" else "patched"
                        console.print(
                            f"  [bold cyan]✎[/bold cyan] [bold]{escape(self.label)}[/bold]"
                            f" {verb} [green]{escape(p)}[/green]"
                        )

                # ---- circuit breaker ----
                h = self._args_hash(tool_name, tool_args)
                if not success:
                    consecutive_failures[h] = consecutive_failures.get(h, 0) + 1
                    console.print(
                        f"  [red]✗[/red] [bold]{escape(self.label)}[/bold]"
                        f" {escape(tool_name)} failed"
                        f" (strike {consecutive_failures[h]}/{self.max_strikes})"
                        f" — {escape(str(result.get('error', '')))[:80]}"
                    )
                    if consecutive_failures[h] >= self.max_strikes:
                        strikes_tripped = True
                        status = "stuck"
                        final_content = f"3 consecutive failures of {tool_name}; aborting"
                        break
                else:
                    consecutive_failures.pop(h, None)

                # ---- feed result back ----
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user",      "content": format_tool_result(result)})
            else:
                status = "max_calls"
                final_content = f"hit max_tool_calls ({self.max_tool_calls})"

        # ---- compact summary line ----
        elapsed = time.time() - start
        icon  = {"ok": "✓", "stuck": "✗", "max_calls": "⊘", "error": "✗"}.get(status, "·")
        color = {"ok": "green", "stuck": "red", "max_calls": "yellow", "error": "red"}.get(status, "white")
        console.print(
            f"[{color}]{icon}[/{color}] [bold]{escape(self.label)}[/bold] | "
            f"{len(tool_calls_log)} calls | "
            f"{prompt_total + gen_total:,} t | {elapsed:.1f}s "
            f"[dim]({status})[/dim]"
        )

        return {
            "status":          status,
            "content":         final_content,
            "thinking":        "\n\n".join(thinking_accum),
            "tool_calls":      tool_calls_log,
            "files_touched":   files_touched,
            "tokens":          {"prompt": prompt_total, "gen": gen_total},
            "elapsed_s":       elapsed,
            "strikes_tripped": strikes_tripped,
        }

    def _execute(self, tool_name, args):
        fn = _dispatch_tool(tool_name)
        if fn is None:
            return {"error": f"unknown tool: {tool_name}"}
        try:
            return fn(args)
        except Exception as e:
            return {"error": str(e)}
