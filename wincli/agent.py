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
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

import tools
from modes import gate_tool
import ui
from ui import console


# Sampling tuned for deterministic tool-call JSON. Small models (e.g. a 9B)
# drift into malformed/invented tool calls at typical chat defaults
# (temperature ~0.7-1.0). presence_penalty is forced to 0 because a high value
# (some modelfiles ship 1.5) penalizes the repeated tokens that structured JSON
# inherently needs ("tool", "path", "args", quotes, braces) and corrupts calls.
AGENT_OPTIONS = {"temperature": 0.15, "top_p": 0.9, "presence_penalty": 0.0}

# Context window floor/ceiling.
#   floor → guarantees the ~3k-char system prompt + a few turns always fit;
#           Ollama's bare default (2048-4096) silently truncates and breaks
#           tool formatting.
#   ceil  → only applied when we fall back to the model's *architectural*
#           context length (which can be enormous, e.g. 262144) — forcing that
#           as num_ctx would OOM the GPU. An explicit modelfile num_ctx is
#           honored as-is (your tested value), never capped by the ceiling.
# Bump these if your model and GPU allow.
AGENT_NUM_CTX_FLOOR = 8192
AGENT_NUM_CTX_CEIL = 16384

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think_blocks(content):
    """Strip all think blocks, including dangling ones starting without <think>."""
    content = THINK_RE.sub("", content)
    content = re.sub(r"^.*?</think>", "", content, flags=re.DOTALL)
    return content


def _strip_thinking(content):
    """Return (thinking, visible). thinking may be empty string."""
    thoughts = "\n".join(m.group(1).strip() for m in re.finditer(r"<think>(.*?)</think>", content, re.DOTALL))
    if not content.strip().startswith("<think>") and "</think>" in content:
        idx = 0
        nesting = 1
        while idx < len(content):
            if content[idx:].startswith("<think>"):
                nesting += 1
                idx += 7
            elif content[idx:].startswith("</think>"):
                nesting -= 1
                if nesting == 0:
                    thoughts = content[:idx].strip()
                    break
                idx += 8
            else:
                idx += 1
    visible = strip_think_blocks(content)
    return thoughts, visible


def _rescue_write_call(raw_json: str):
    """Rescue a write_file / append_file tool call when json.loads fails.

    Models stream HTML/code inside JSON strings. Ollama pre-decodes escape
    sequences in message.content chunks, so the accumulated buffer ends up
    with literal '"' chars inside the content field (from HTML attributes
    like class="btn") which breaks json.loads. append_file is covered too:
    its section chunks carry the same quote/newline-heavy payload.

    Strategy: extract tool/path by regex, extract content by rfind-ing the
    closing '"}}' sentinel at the end of the JSON object.
    """
    tool_m = re.search(r'"tool"\s*:\s*"(write_file|append_file)"', raw_json)
    if not tool_m:
        return None
    tool_name = tool_m.group(1)

    # Path is short and usually well-escaped — use quoted-string regex
    path_m = re.search(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"', raw_json)
    if not path_m:
        return None
    path = path_m.group(1)

    # Find where the content value starts
    cm = re.search(r'"content"\s*:\s*"', raw_json)
    if not cm:
        return None

    rest = raw_json[cm.end():]
    # Content ends just before the closing "}} of the JSON object.
    # rfind gives us the LAST occurrence, which is the JSON's own closing.
    end = rest.rfind('"}}')
    if end == -1:
        end = rest.rfind('"}')
    if end == -1:
        return None

    raw_content = rest[:end]
    # Decode escape sequences the model did use correctly
    raw_content = raw_content.replace('\\n', '\n')
    raw_content = raw_content.replace('\\t', '\t')
    raw_content = raw_content.replace('\\"', '"')
    raw_content = raw_content.replace('\\\\', '\\')

    return {"tool": tool_name, "args": {"path": path, "content": raw_content}}


def _extract_embedded_json(text):
    """Find the first {"tool": ...} object embedded anywhere in free text.

    Returns (tool_call_dict, prose_before) or (None, None).
    Uses a bracket counter so it handles nested objects correctly.
    """
    for m in re.finditer(r'\{"tool"\s*:', text):
        start = m.start()
        depth = 0
        for i, ch in enumerate(text[start:]):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:start + i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and "tool" in parsed:
                            return parsed, text[:start].strip()
                    except json.JSONDecodeError:
                        rescued = _rescue_write_call(candidate)
                        if rescued:
                            return rescued, text[:start].strip()
                    break
    return None, None


def parse_tool_call(response_content):
    """Parse a tool call from the model response.

    Returns (tool_call_dict | None, prose_prefix | "").
    Prose prefix is non-empty when the tool call was embedded inside text
    rather than sent as a standalone block — the caller should display it.

    Priority:
      1. ```json … ``` fenced block (the correct format)
      2. Bare JSON at the start of the response
      3. {"tool":…} object embedded anywhere inside prose
    """
    # 1. Fenced block (preferred / correct format)
    json_match = re.search(r"```json\s*(.*?)\s*```", response_content, re.DOTALL)
    if json_match:
        raw = json_match.group(1).strip()
        try:
            return json.loads(raw), ""
        except json.JSONDecodeError:
            rescued = _rescue_write_call(raw)
            if rescued:
                return rescued, ""

    # 2. Bare JSON covering the whole response (no fence)
    try:
        parsed = json.loads(response_content.strip())
        if isinstance(parsed, dict) and "tool" in parsed:
            return parsed, ""
    except json.JSONDecodeError:
        # Large write_file calls often fail json.loads because the model emits
        # raw newlines / unescaped quotes inside a multi-line content value.
        # The byte-level rescue handles exactly this — and the brace-counting
        # _extract_embedded_json (step 3) can't, because CSS/JS braces in the
        # content desync its depth counter. Try the rescue here before step 3.
        rescued = _rescue_write_call(response_content.strip())
        if rescued:
            return rescued, ""

    # 3. JSON embedded inside prose — extract and surface the preceding text
    embedded, prose = _extract_embedded_json(response_content)
    if embedded:
        return embedded, prose or ""

    return None, ""


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
    if result.get("status") == "started":
        return f"[PID {result['pid']}] {result['message']}"
    if "numbered" in result:
        return f"File contents (with line numbers):\n{result['numbered']}"
    if "content" in result:
        return f"File contents:\n{result['content']}"
    if result.get("status") == "patched":
        return f"Patched {result['path'].replace(chr(92), '/')} (variant {result.get('variant','?')})"
    if result.get("status") == "ok":
        return f"Wrote file {result['path'].replace(chr(92), '/')}"
    if result.get("status") == "appended":
        return f"Appended to {result['path'].replace(chr(92), '/')}"
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
    """Return (context_window, configured).

    configured=True → the modelfile explicitly set num_ctx; trust it as-is
        (it's the value the user has actually tested on their hardware).
    configured=False → we fell back to the model's architectural context_length
        (which can be huge, e.g. 262144) or the 2048 default; callers should
        clamp these to avoid OOM.
    """
    try:
        info = ollama.show(model_name)
        params = info.get("parameters", "")
        if isinstance(params, str):
            for line in params.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "num_ctx":
                    return int(parts[1]), True
        modelinfo = info.get("modelinfo", {})
        if isinstance(modelinfo, dict):
            for k, v in modelinfo.items():
                if k.endswith(".context_length"):
                    return int(v), False
    except Exception:
        pass
    return 2048, False


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
        is_thinking = False
        if tail and "<think>" in tail:
            last_think = tail.rfind("<think>")
            last_unthink = tail.rfind("</think>")
            if last_think > last_unthink:
                is_thinking = True

        sp = _THINK_SPIN[tick % len(_THINK_SPIN)]
        if is_thinking:
            lines.append(f"[magenta]{sp}[/magenta] [magenta]thinking[/magenta] [dim](inside <think>)[/dim]")
        else:
            lines.append(f"[blue]{sp}[/blue] [blue]generating[/blue]")
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
    "Patched ", "Wrote file ", "Appended to ",
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
    detected_ctx, ctx_configured = get_context_limit(model)
    if ctx_configured:
        # Honor the modelfile's num_ctx (the user's tested value); only ensure
        # it isn't so small it truncates the system prompt.
        context_limit = max(detected_ctx, AGENT_NUM_CTX_FLOOR)
    else:
        # Architectural / default fallback — clamp so a huge arch length (e.g.
        # 262144) doesn't OOM the GPU when forced as num_ctx.
        context_limit = min(max(detected_ctx, AGENT_NUM_CTX_FLOOR),
                            AGENT_NUM_CTX_CEIL)
    options = {**AGENT_OPTIONS, "num_ctx": context_limit}
    consecutive_failures = {}  # args_hash → count
    focus = bool(getattr(state, "focus", False)) if state is not None else False
    listed_dirs: set = set()   # parent dirs confirmed via list_dir this turn
    verified_files: set = set()  # files read/written this turn (known to exist)

    _MUTATING_TOOLS = {"write_file", "append_file", "patch_file", "remove_file"}

    while True:
        escaped = _prepare_messages(messages)

        content_parts = []
        token_count = 0
        tick = 0
        start_time = time.time()
        detected_tool, detected_files = None, []
        final_eval = final_eval_dur = final_prompt = 0

        interrupted = False
        in_reasoning = False
        with Live(Text("connecting..."), refresh_per_second=12, console=console) as live:
            try:
                stream = ollama.chat(model=model, messages=escaped, stream=True,
                                     options=options)
                for chunk in stream:
                    reasoning = ""
                    content = ""
                    if isinstance(chunk, dict):
                        msg = chunk.get("message", {})
                        content = msg.get("content", "") or ""
                        reasoning = msg.get("reasoning_content", "") or ""
                    else:
                        msg = getattr(chunk, "message", None)
                        content = getattr(msg, "content", "") if msg else ""
                        reasoning = getattr(msg, "reasoning_content", "") if msg and hasattr(msg, "reasoning_content") else ""

                    token_parts = []
                    if reasoning:
                        if not in_reasoning:
                            token_parts.append("<think>")
                            in_reasoning = True
                        token_parts.append(reasoning)
                    elif content:
                        if in_reasoning:
                            token_parts.append("</think>\n")
                            in_reasoning = False
                        token_parts.append(content)

                    tok = "".join(token_parts)
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
                
                if in_reasoning:
                    content_parts.append("</think>\n")
                    in_reasoning = False

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

        # Separate thinking tag (if any) so it doesn't confuse parsing/persist
        thoughts, visible = _strip_thinking(content)
        if thoughts and not focus:
            console.print(Panel(thoughts[:1500], title="💭 thinking",
                                border_style="dim magenta"))

        # Strip all think tags from content immediately before tool parsing or logging
        content = strip_think_blocks(content)

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

        tool_call, embedded_prose = parse_tool_call(visible)

        # Model sent prose + tool call in the same response: show the prose
        # as an intermediate message before executing the tool.
        if tool_call and embedded_prose:
            console.print(Panel(embedded_prose, title="🤖 assistant (message)",
                                subtitle=subtitle, border_style="green"))
            console.print("[dim]↳ tool call detected inside message — executing it now[/dim]")

        if tool_call and isinstance(tool_call, dict) and "tool" in tool_call:
            tool_name = tool_call.get("tool")
            tool_args = tool_call.get("args", {}) or {}

            # Track list_dir calls so we know which dirs have been verified
            if tool_name == "list_dir":
                p = tool_args.get("path", "")
                if p:
                    from pathlib import Path as _Path
                    listed_dirs.add(str(_Path(p).resolve()))

            # Pre-check: block mutating tools unless the file's location was
            # verified this turn — either via list_dir on the parent, or because
            # the file was already read/written this turn (so we know it exists
            # and its exact name). This avoids a needless "list_dir wall" right
            # after the agent has already read the file it wants to patch.
            if tool_name in _MUTATING_TOOLS:
                file_path = tool_args.get("path", "")
                if file_path:
                    from pathlib import Path as _Path
                    resolved = str(_Path(file_path).resolve())
                    parent = str(_Path(resolved).parent)
                    if parent not in listed_dirs and resolved not in verified_files:
                        warn = (
                            f"RULE VIOLATION: you called '{tool_name}' on '{file_path}' "
                            f"without first reading it or calling list_dir on its parent "
                            f"directory ('{parent}'). You MUST read_file it or list_dir that "
                            f"directory first to confirm the file exists and its exact name is correct."
                        )
                        console.print(f"[yellow]pre-check: list_dir required before {tool_name}[/yellow]")
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": warn})
                        continue

            # Permission gate
            if state is not None and not gate_tool(state, tool_name, tool_args):
                console.print("[red]denied by user — stopping turn[/red]")
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user",
                                 "content": "The user didn't accept the request. "
                                            "They may want to change the approach."})
                if session_log:
                    session_log.log_step(kind="assistant", content=visible,
                                         prompt_tokens=prompt_tokens, gen_tokens=gen_tokens,
                                         elapsed_s=elapsed,
                                         tool_call={"name": tool_name, "args": tool_args},
                                         tool_result={"error": "denied by user"})
                return

            # Snapshot file *before* mutating tools execute
            if snapshot_mgr is not None and tool_name in ("write_file", "append_file", "patch_file", "remove_file"):
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
                console.print(f"[bold red]✗ tool[/bold red] [red]{tool_name}[/red] - error "
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
                # Remember files we've now confirmed to exist this turn, so a
                # follow-up patch/write doesn't trip the list_dir pre-check.
                if tool_name in ("read_file", "write_file", "append_file", "patch_file"):
                    rp = tool_args.get("path")
                    if rp:
                        from pathlib import Path as _Path
                        verified_files.add(str(_Path(rp).resolve()))
                display_path = (tool_args.get("path") or tool_args.get("url")
                                or (tool_args.get("command") or "")[:60] or "-")
                console.print(f"[bold green]✓ tool[/bold green] [green]{tool_name}[/green] - {display_path}")

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
