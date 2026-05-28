"""Agent loop: send → parse → gate → execute → log → loop.

Features layered on top of the original loop:
  - <think>...</think> tags are stripped from tool-parsing and rendered
    separately so the user can see thinking without it polluting context.
  - Circuit breaker: 3 consecutive failures of the same (tool, args_hash)
    stop the loop and call the reflect skill automatically.
  - Permission gating via modes.gate_tool (respects /mode setting).
  - Per-step persistence via persist.SessionLog.
  - Dispatch falls through to extra_tools.py if the tool isn't in CORE_TOOLS.
"""

import hashlib
import importlib
import json
import re
import time

import ollama
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

import tools
from modes import gate_tool

console = Console()


THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(content):
    """Return (thinking, visible). thinking may be empty string."""
    thoughts = "\n".join(m.group(1).strip() for m in re.finditer(r"<think>(.*?)</think>", content, re.DOTALL))
    visible = THINK_RE.sub("", content).strip()
    return thoughts, visible


def parse_tool_call(response_content):
    """Parse a tool call JSON block from the model response. Thinking
    tags must be stripped before calling this."""
    json_match = re.search(r"```json\s*(.*?)\s*```", response_content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            return None
    try:
        return json.loads(response_content.strip())
    except json.JSONDecodeError:
        return None


def _dispatch_tool(tool_name):
    """Return the callable for tool_name, looking at CORE_TOOLS first and
    extra_tools.py second."""
    if tool_name in tools.CORE_TOOLS:
        return tools.CORE_TOOLS[tool_name]
    # Try extra_tools.py (created by /skill add_tool)
    try:
        extra = importlib.import_module("extra_tools")
        importlib.reload(extra)  # pick up additions made mid-session
        fn = getattr(extra, tool_name, None)
        if callable(fn):
            return fn
    except ModuleNotFoundError:
        pass
    return None


def _error_hint(tool_name, args, exc):
    """Best-effort suggestion to help the model recover."""
    msg = str(exc).lower()
    if isinstance(exc, FileNotFoundError) or "no such file" in msg or "cannot find" in msg:
        p = args.get("path") or args.get("url") or ""
        return f"path not found: '{p}'. check spelling / use list_dir to verify."
    if isinstance(exc, PermissionError) or "permission denied" in msg:
        return "permission denied. try a different path or check file ownership."
    if "timeout" in msg or "timed out" in msg:
        return "operation timed out. consider a smaller payload or retry."
    if "json" in msg and tool_name == "patch_file":
        return "malformed patch args. re-read the file and retry with exact strings."
    if "connection" in msg or "network" in msg:
        return "network/connection issue. retry or check the URL/host."
    return None


def execute_tool(tool_name, args):
    fn = _dispatch_tool(tool_name)
    if fn is None:
        return {"error": f"unknown tool: {tool_name}",
                "hint": "valid tools: run_command, read_file, write_file, "
                        "patch_file, list_dir, search_file, http_get"}
    try:
        return fn(args)
    except Exception as e:
        out = {"error": str(e)}
        hint = _error_hint(tool_name, args, e)
        if hint:
            out["hint"] = hint
        return out


def format_tool_result(result):
    if "error" in result:
        hint = f"\nHint: {result['hint']}" if result.get("hint") else ""
        return f"Tool call failed: {result['error']}{hint}"
    if "stdout" in result or "stderr" in result:
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        rc = result.get("returncode", 0)
        parts = [f"returncode: {rc}"]
        if stdout:
            parts.append(f"STDOUT:\n{stdout}")
        if stderr:
            parts.append(f"STDERR:\n{stderr}")
        return "\n".join(parts)
    if "numbered" in result:
        return f"File contents (with line numbers):\n{result['numbered']}"
    if "content" in result:
        return f"File contents:\n{result['content']}"
    if result.get("status") == "patched":
        return f"Patched {result['path']} (variant {result.get('variant','?')})"
    if result.get("status") == "ok":
        return f"Wrote file {result['path']}"
    if "entries" in result:
        return f"Directory contents: {', '.join(result['entries'])}"
    if "matches" in result:
        if result["matches"]:
            return f"Found {len(result['matches'])} matches:\n" + "\n".join(
                f"Line {m['line']}: {m['content']}" for m in result["matches"])
        return "No matches found"
    if "body" in result:
        return f"HTTP {result.get('status_code','?')}\n{result['body']}"
    return str(result)


def get_context_limit(model_name):
    try:
        info = ollama.show(model_name)
        params = info.get("parameters", "")
        if isinstance(params, str):
            for line in params.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "num_ctx":
                    return int(parts[1])
        modelinfo = info.get("modelinfo", {})
        if isinstance(modelinfo, dict):
            for k, v in modelinfo.items():
                if k.endswith(".context_length"):
                    return int(v)
    except Exception:
        pass
    return 2048


def _args_hash(tool_name, args):
    try:
        s = json.dumps(args, sort_keys=True, ensure_ascii=False)
    except Exception:
        s = str(args)
    return hashlib.md5(f"{tool_name}|{s}".encode("utf-8")).hexdigest()[:10]


def _detect_partial_tool(text):
    m = re.search(r'"tool"\s*:\s*"(\w+)"', text)
    if not m:
        return None, []
    paths = re.findall(r'"(?:path|url)"\s*:\s*"([^"]+)"', text)
    return m.group(1), paths[:3]


_THINK_SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_TOOL_SPIN = "◐◓◑◒"


def _wrap_tail(tail, width=140):
    """Take last ~width chars from tail, word-bounded, single line."""
    if not tail:
        return ""
    flat = tail.replace("\n", " ⏎ ")
    if len(flat) <= width:
        return flat
    snip = flat[-width:]
    # try to start at a space so we don't cut mid-word
    space = snip.find(" ")
    if 0 < space < 20:
        snip = snip[space + 1:]
    return "…" + snip


def _live_status(token_count, elapsed, detected_tool, files, tail, done, *, tick=0):
    tps = token_count / elapsed if elapsed > 0 else 0
    lines = []
    if done:
        lines.append("✓ [bold green]done[/bold green]")
    elif detected_tool:
        sp = _TOOL_SPIN[tick % len(_TOOL_SPIN)]
        lines.append(f"[cyan]{sp}[/cyan] [cyan]calling[/cyan] "
                     f"[yellow]{escape(detected_tool)}[/yellow]"
                     + (f" → {escape(', '.join(files))}" if files else ""))
    else:
        sp = _THINK_SPIN[tick % len(_THINK_SPIN)]
        lines.append(f"[blue]{sp}[/blue] [blue]thinking[/blue]")
    lines.append(f"   ⚡ [dim]{tps:.1f} t/s | {token_count} t | {elapsed:.1f}s[/dim]")
    if not done and tail:
        lines.append(f"   [dim]{escape(_wrap_tail(tail))}[/dim]")
    return Text.from_markup("\n".join(lines))


def _ctx_warning_markup(consumed, limit):
    """Return a colored fragment for the subtitle reflecting remaining context."""
    if limit <= 0:
        return None
    pct = consumed / limit
    remaining = max(0, limit - consumed)
    if pct >= 0.9:
        return f"[bold red]⚠ ctx {consumed}/{limit} ({remaining} left)[/bold red]"
    if pct >= 0.75:
        return f"[yellow]ctx {consumed}/{limit} ({remaining} left)[/yellow]"
    return None


TOOL_RESULT_PREFIXES = (
    "Tool call failed:",
    "File contents",
    "Directory contents:",
    "Patched ", "Wrote file ",
    "Found ", "No matches",
    "returncode:",
    "HTTP ",
)

OLD_TURNS_THRESHOLD = 5  # tool results from older than N user-turns get summarized


def _is_tool_result(content):
    return any(content.startswith(p) for p in TOOL_RESULT_PREFIXES)


def _summarize_tool_result(content):
    """One-line replacement for an old tool result."""
    first_line = content.splitlines()[0] if content else ""
    # Take just the type marker + a brief hint
    if first_line.startswith("File contents"):
        return "[tool: file contents — summarized away]"
    if first_line.startswith("returncode:"):
        return f"[tool: command result — {first_line[:60]} — summarized away]"
    if first_line.startswith("Patched") or first_line.startswith("Wrote file"):
        return f"[tool: {first_line[:80]} — summarized away]"
    if first_line.startswith("Tool call failed:"):
        return f"[tool: {first_line[:80]} — summarized away]"
    return "[tool result — summarized away]"


def _prepare_messages(messages):
    """Escape backslashes (Windows quirk) and summarize tool results
    older than OLD_TURNS_THRESHOLD user turns."""
    # First, count user-turn distance for each message
    out = []
    user_turns_after = []   # how many real user turns come after each msg
    # Walk backwards counting "real" user messages (non-tool-result)
    seen_real_user = 0
    distances = [0] * len(messages)
    for i in range(len(messages) - 1, -1, -1):
        distances[i] = seen_real_user
        m = messages[i]
        if m.get("role") == "user" and not _is_tool_result(m.get("content", "")):
            seen_real_user += 1

    for i, m in enumerate(messages):
        content = m.get("content", "")
        if m.get("role") == "user" and _is_tool_result(content) \
                and distances[i] > OLD_TURNS_THRESHOLD:
            content = _summarize_tool_result(content)
        if m.get("role") == "user":
            content = content.replace("\\", "\\\\")
        out.append({"role": m.get("role"), "content": content})
    return out


def run_agent_loop(messages, model, *, state=None, session_log=None,
                   reflect_callback=None, snapshot_mgr=None):
    """Mutates `messages` in-place. state and session_log are optional but
    recommended; reflect_callback is called when the circuit breaker fires.
    snapshot_mgr (if provided) snapshots files before write/patch.

    Ctrl+C during a turn cancels the turn cleanly (returns without exiting)."""
    context_limit = get_context_limit(model)
    consecutive_failures = {}  # args_hash → count
    focus = bool(getattr(state, "focus", False)) if state is not None else False

    while True:
        escaped = _prepare_messages(messages)

        content_parts = []
        token_count = 0
        tick = 0
        start_time = time.time()
        detected_tool, detected_files = None, []
        final_eval = final_eval_dur = final_prompt = 0

        interrupted = False
        with Live(Text("connecting..."), refresh_per_second=12, console=console) as live:
            try:
                stream = ollama.chat(model=model, messages=escaped, stream=True)
                for chunk in stream:
                    tok = chunk.get("message", {}).get("content", "") if isinstance(chunk, dict) \
                        else getattr(chunk.message, "content", "")
                    if tok:
                        content_parts.append(tok)
                        token_count += 1
                    acc = "".join(content_parts)
                    if not detected_tool:
                        detected_tool, detected_files = _detect_partial_tool(acc)
                    if isinstance(chunk, dict):
                        if chunk.get("done"):
                            final_eval = chunk.get("eval_count", 0) or 0
                            final_eval_dur = chunk.get("eval_duration", 0) or 0
                            final_prompt = chunk.get("prompt_eval_count", 0) or 0
                    tick += 1
                    live.update(_live_status(token_count, time.time() - start_time,
                                             detected_tool, detected_files, acc, False,
                                             tick=tick))
                live.update(_live_status(token_count, time.time() - start_time,
                                         detected_tool, detected_files,
                                         "".join(content_parts), True, tick=tick))
                time.sleep(0.1)
            except KeyboardInterrupt:
                interrupted = True
            except Exception as e:
                console.print(Panel(f"[red]model call failed: {escape(str(e))}[/red]",
                                    border_style="red"))
                return

        if interrupted:
            console.print(Panel(
                "[yellow]turn cancelled by user (Ctrl+C).[/yellow]\n"
                "[dim]partial response discarded; session preserved.[/dim]",
                border_style="yellow"))
            # Append a marker so the agent knows on the next prompt that
            # something was cut short.
            messages.append({"role": "user",
                             "content": "[USER INTERRUPTED THE PREVIOUS RESPONSE]"})
            return

        elapsed = time.time() - start_time
        content = "".join(content_parts)
        content = THINK_RE.sub("", content)

        # Separate thinking tag (if any) so it doesn't confuse parsing/persist
        thoughts, visible = _strip_thinking(content)
        if thoughts and not focus:
            console.print(Panel(thoughts[:1500], title="💭 thinking",
                                border_style="dim magenta"))

        # Stats subtitle (consumed / window)
        gen_tokens = final_eval or token_count
        prompt_tokens = final_prompt
        consumed = prompt_tokens + gen_tokens
        remaining = max(0, context_limit - consumed)
        tps = gen_tokens / elapsed if elapsed > 0 else 0
        warn = _ctx_warning_markup(consumed, context_limit)
        subtitle = (f"⚡ {tps:.1f} t/s | prompt {prompt_tokens} | gen {gen_tokens} | "
                    f"window {consumed}/{context_limit} ({remaining} left)")
        if warn:
            subtitle = f"{subtitle}  {warn}"

        tool_call = parse_tool_call(visible)

        if tool_call and isinstance(tool_call, dict) and "tool" in tool_call:
            tool_name = tool_call.get("tool")
            tool_args = tool_call.get("args", {}) or {}

            # Permission gate
            if state is not None and not gate_tool(state, tool_name, tool_args):
                console.print("[red]denied by user[/red]")
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user",
                                 "content": "Tool call denied by user. Adjust your approach or ask for guidance."})
                if session_log:
                    session_log.log_step(kind="assistant", content=visible,
                                         prompt_tokens=prompt_tokens, gen_tokens=gen_tokens,
                                         elapsed_s=elapsed,
                                         tool_call={"name": tool_name, "args": tool_args},
                                         tool_result={"error": "denied by user"})
                continue

            # Snapshot file *before* mutating tools execute
            if snapshot_mgr is not None and tool_name in ("write_file", "patch_file"):
                p = tool_args.get("path")
                if p:
                    try:
                        snapshot_mgr.take(p, "write" if tool_name == "write_file" else "patch")
                    except Exception:
                        pass

            try:
                result = execute_tool(tool_name, tool_args)
            except KeyboardInterrupt:
                console.print(Panel(
                    "[yellow]turn cancelled during tool execution (Ctrl+C).[/yellow]",
                    border_style="yellow"))
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user",
                                 "content": "[USER INTERRUPTED DURING TOOL EXECUTION]"})
                return
            is_error = "error" in result or result.get("returncode", 0) not in (0, None)

            # Circuit breaker
            h = _args_hash(tool_name, tool_args)
            if is_error:
                consecutive_failures[h] = consecutive_failures.get(h, 0) + 1
                console.print(f"[bold red]tool[/bold red] {tool_name} - error "
                              f"(strike {consecutive_failures[h]}/3)")
                if consecutive_failures[h] >= 3:
                    console.print(Panel(
                        f"[red]circuit breaker tripped on {tool_name}.[/red]\n"
                        "stopping the loop and triggering /reflect.",
                        border_style="red"))
                    if reflect_callback:
                        reflect_callback()
                    return
            else:
                consecutive_failures.pop(h, None)
                display_path = (tool_args.get("path") or tool_args.get("url")
                                or (tool_args.get("command") or "")[:60] or "-")
                console.print(f"[bold cyan]tool[/bold cyan] {tool_name} - {display_path}")

            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": format_tool_result(result)})

            if session_log:
                session_log.log_step(kind="assistant", content=visible,
                                     prompt_tokens=prompt_tokens, gen_tokens=gen_tokens,
                                     elapsed_s=elapsed,
                                     tool_call={"name": tool_name, "args": tool_args},
                                     tool_result=result)
            continue

        # No tool call → final answer
        messages.append({"role": "assistant", "content": content})
        if focus:
            console.print(visible)
            console.print(Text.from_markup(f"[dim]{subtitle}[/dim]"))
        else:
            console.print(Panel(visible, title="🤖 assistant", subtitle=subtitle,
                                border_style="green"))
        if session_log:
            session_log.log_step(kind="assistant", content=visible,
                                 prompt_tokens=prompt_tokens, gen_tokens=gen_tokens,
                                 elapsed_s=elapsed)
        return
