"""Isolated sub-agent for multi-agent flows.

A SubAgent is a stripped-down version of run_agent_loop:
  - Independent conversation (no shared history)
  - Tools restricted to a whitelist
  - Configurable num_ctx + keep_alive
  - Compact one-line progress display
  - Returns a structured result with token/time stats and files touched

Used by the multi-agent plan flow (planner / reviewer / executor / verifier).
"""

import hashlib
import json
import re
import time
from typing import Optional, List, Dict, Any

import ollama
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.text import Text

import tools as tools_mod
from agent import parse_tool_call, format_tool_result, _strip_thinking, _dispatch_tool

console = Console()


THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


class SubAgent:
    """An isolated agent with its own context and tool whitelist."""

    def __init__(self, *, model: str, system_prompt: str,
                 tools_whitelist: Optional[List[str]] = None,
                 num_ctx: int = 8192, keep_alive: str = "10m",
                 max_tool_calls: int = 15, max_strikes: int = 3,
                 label: str = "subagent", temperature: float = 0.2):
        self.model = model
        self.system_prompt = system_prompt
        self.whitelist = set(tools_whitelist) if tools_whitelist else None
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.max_tool_calls = max_tool_calls
        self.max_strikes = max_strikes
        self.label = label
        self.temperature = temperature

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

    def run(self, user_message: str) -> Dict[str, Any]:
        """Run the subagent until it stops calling tools or hits limits.

        Returns:
            {
              "status": "ok" | "stuck" | "max_calls" | "error",
              "content": str,           # final visible answer
              "thinking": str,          # all <think> blocks concatenated
              "tool_calls": [           # list of executed calls
                  {"name": str, "args": dict, "result": dict, "success": bool}
              ],
              "files_touched": [str],   # paths from write/patch tools
              "tokens": {"prompt": int, "gen": int},
              "elapsed_s": float,
              "strikes_tripped": bool,
            }
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        tool_calls: List[Dict[str, Any]] = []
        files_touched: List[str] = []
        consecutive_failures: Dict[str, int] = {}
        prompt_total = 0
        gen_total = 0
        start = time.time()
        status = "ok"
        strikes_tripped = False
        final_content = ""
        thinking_accum = []

        live_state = {"phase": "starting", "step": 0}

        with Live(self._render(live_state), refresh_per_second=8, console=console) as live:
            for step in range(self.max_tool_calls + 1):
                live_state["step"] = step
                live_state["phase"] = "thinking"
                live.update(self._render(live_state))

                # 1) call model
                try:
                    escaped = []
                    for m in messages:
                        if m["role"] == "user":
                            escaped.append({"role": "user",
                                            "content": m["content"].replace("\\", "\\\\")})
                        else:
                            escaped.append(m)
                    resp = ollama.chat(
                        model=self.model,
                        messages=escaped,
                        stream=False,
                        keep_alive=self.keep_alive,
                        options={"num_ctx": self.num_ctx,
                                 "temperature": self.temperature},
                    )
                except Exception as e:
                    status = "error"
                    final_content = f"model call failed: {e}"
                    break

                if isinstance(resp, dict):
                    content = resp.get("message", {}).get("content", "") or ""
                    prompt_total += resp.get("prompt_eval_count", 0) or 0
                    gen_total += resp.get("eval_count", 0) or 0
                else:
                    content = getattr(resp.message, "content", "") or ""
                    prompt_total += getattr(resp, "prompt_eval_count", 0) or 0
                    gen_total += getattr(resp, "eval_count", 0) or 0

                thoughts, visible = _strip_thinking(content)
                if thoughts:
                    thinking_accum.append(thoughts)

                tool_call = parse_tool_call(visible)

                # 2) no tool call → final answer
                if not (tool_call and isinstance(tool_call, dict) and "tool" in tool_call):
                    final_content = visible
                    break

                tool_name = tool_call.get("tool")
                tool_args = tool_call.get("args", {}) or {}
                live_state["phase"] = f"calling {tool_name}"
                live_state["last_path"] = tool_args.get("path") or tool_args.get("url") or ""
                live.update(self._render(live_state))

                # 3) whitelist check
                if not self._gate_tool(tool_name):
                    result = {"error": f"tool '{tool_name}' is not in this subagent's whitelist",
                              "hint": f"allowed: {sorted(self.whitelist) if self.whitelist else 'all'}"}
                    success = False
                else:
                    result = self._execute(tool_name, tool_args)
                    success = "error" not in result and result.get("returncode", 0) in (0, None)

                tool_calls.append({"name": tool_name, "args": tool_args,
                                   "result": result, "success": success})

                if success and tool_name in ("write_file", "patch_file"):
                    p = tool_args.get("path")
                    if p and p not in files_touched:
                        files_touched.append(p)

                # 4) strikes
                h = self._args_hash(tool_name, tool_args)
                if not success:
                    consecutive_failures[h] = consecutive_failures.get(h, 0) + 1
                    if consecutive_failures[h] >= self.max_strikes:
                        strikes_tripped = True
                        status = "stuck"
                        final_content = f"3 consecutive failures of {tool_name}; aborting"
                        break
                else:
                    consecutive_failures.pop(h, None)

                # 5) feed result back
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": format_tool_result(result)})
            else:
                status = "max_calls"
                final_content = f"hit max_tool_calls ({self.max_tool_calls})"

        elapsed = time.time() - start
        # Print compact summary line
        icon = {"ok": "✓", "stuck": "✗", "max_calls": "⊘", "error": "✗"}.get(status, "·")
        color = {"ok": "green", "stuck": "red", "max_calls": "yellow", "error": "red"}.get(status, "white")
        console.print(
            f"[{color}]{icon}[/{color}] [bold]{self.label}[/bold] | "
            f"{len(tool_calls)} calls | "
            f"{prompt_total + gen_total:,} t | {elapsed:.1f}s "
            f"[dim]({status})[/dim]"
        )

        return {
            "status": status,
            "content": final_content,
            "thinking": "\n\n".join(thinking_accum),
            "tool_calls": tool_calls,
            "files_touched": files_touched,
            "tokens": {"prompt": prompt_total, "gen": gen_total},
            "elapsed_s": elapsed,
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

    def _render(self, state):
        spinner = "⡏⡟⡯⣏"[state.get("step", 0) % 4]
        path = state.get("last_path") or ""
        path_str = f" [dim]→ {escape(path)[:50]}[/dim]" if path else ""
        return Text.from_markup(
            f"  [cyan]{spinner}[/cyan] [bold]{self.label}[/bold]: "
            f"{state.get('phase','')}{path_str}"
        )
