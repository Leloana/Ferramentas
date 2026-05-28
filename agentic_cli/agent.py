import json
import re
import time
import ollama
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
import tools

console = Console()


def parse_tool_call(response_content):
    """Parse tool call from model response"""
    json_match = re.search(r'```json\s*(.*?)\s*```', response_content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None

    # Fallback to try parsing the entire response as JSON
    try:
        return json.loads(response_content.strip())
    except json.JSONDecodeError:
        return None


def execute_tool(tool_name, args):
    """Execute the requested tool and return result"""
    tool_func = getattr(tools, tool_name, None)
    if tool_func and callable(tool_func):
        try:
            return tool_func(args)
        except Exception as e:
            return {"error": str(e)}
    return {"error": f"Unknown tool: {tool_name}"}


def format_tool_result(result):
    """Format tool result as a message for the model"""
    if "error" in result:
        return f"Tool call failed: {result['error']}"

    if "stdout" in result or "stderr" in result:
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        ret = []
        if stdout:
            ret.append(f"STDOUT:\n{stdout}")
        if stderr:
            ret.append(f"STDERR:\n{stderr}")
        if not stdout and not stderr:
            ret.append("Command executed with no output.")
        return "\n".join(ret)
    elif "content" in result:
        return f"File contents:\n{result['content']}"
    elif result.get("status") == "patched":
        return f"Patched file {result['path']} successfully"
    elif result.get("status") == "ok":
        return f"Wrote file {result['path']} successfully"
    elif "entries" in result:
        return f"Directory contents: {', '.join(result['entries'])}"
    elif "matches" in result:
        if result["matches"]:
            return f"Found {len(result['matches'])} matches:\n" + "\n".join(
                f"Line {m['line']}: {m['content']}" for m in result["matches"]
            )
        return "No matches found"
    elif "body" in result:
        return result["body"]
    return str(result)


def get_context_limit(model_name):
    """Retrieve context limit for the model from Ollama API"""
    try:
        info = ollama.show(model_name)
        parameters = info.get("parameters", "")
        if isinstance(parameters, str):
            for line in parameters.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "num_ctx":
                    return int(parts[1])

        modelinfo = info.get("modelinfo", {})
        if isinstance(modelinfo, dict):
            for key, val in modelinfo.items():
                if key.endswith(".context_length"):
                    return int(val)
    except Exception:
        pass
    return 2048


def make_stats_subtitle(response, context_limit, color="cyan"):
    """Create a formatted statistics subtitle showing token metrics and context window"""
    eval_count = getattr(response, "eval_count", 0) or 0
    eval_duration = getattr(response, "eval_duration", 0) or 0
    prompt_eval_count = getattr(response, "prompt_eval_count", 0) or 0

    tokens_per_sec = 0.0
    if eval_duration > 0:
        tokens_per_sec = eval_count / (eval_duration / 1e9)

    consumed = prompt_eval_count + eval_count
    remaining = max(0, context_limit - consumed)

    return f"[dim {color}]⚡ {tokens_per_sec:.1f} t/s | Prompt: {prompt_eval_count} t | Gen: {eval_count} t | Janela: {consumed}/{context_limit} t ({remaining} rest.)[/dim {color}]"


def make_stats_subtitle_from_tracking(context_limit, token_count, elapsed, color="cyan"):
    """Create a formatted statistics subtitle from client-side tracking data"""
    tps = token_count / elapsed if elapsed > 0 else 0
    return f"[dim {color}]⚡ {tps:.1f} t/s | Tokens: {token_count} | Elapsed: {elapsed:.1f}s[/dim {color}]"


def _detect_context_kind(messages):
    """Figure out what kind of context the model is working with."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if any(kw in content for kw in [
                "File contents:", "STDOUT:", "STDERR:", "Directory contents:",
                "Found ", "Wrote file", "Tool call failed:", "No matches",
                "Command executed", "Matches found:",
            ]):
                return "consuming_file"
            return "thinking"
    return "thinking"


def _detect_tool_and_files(accumulated_text):
    """Try to detect tool name and file paths from a partial JSON tool call."""
    tool_match = re.search(r'"tool"\s*:\s*"(\w+)"', accumulated_text)
    if not tool_match:
        return None, []

    tool_name = tool_match.group(1)
    files = []

    # path argument for file-based tools
    path_matches = re.findall(r'"path"\s*:\s*"([^"]+)"', accumulated_text)
    files.extend(path_matches)

    # url argument for http_get
    url_matches = re.findall(r'"url"\s*:\s*"([^"]+)"', accumulated_text)
    files.extend(url_matches)

    # command argument may contain paths
    cmd_matches = re.findall(r'"command"\s*:\s*"([^"]+)"', accumulated_text)
    for cmd in cmd_matches:
        # Extract likely file paths from the command string
        pathlike = re.findall(r'[A-Za-z]:\\[^\s"\']+|\\[^\s"\']+\.[a-zA-Z]{1,4}|\.?[/\\][^\s"\']+\.[a-zA-Z]{1,4}', cmd)
        files.extend(pathlike)

    return tool_name, files


from rich.text import Text
from rich.markup import escape

def _build_live_display(context_kind, token_count, elapsed, detected_tool, detected_files, accumulated, is_done):
    """Build the live display renderable."""
    tps = token_count / elapsed if elapsed > 0 else 0
    lines = []

    if is_done:
        lines.append("✓ [bold green]Done[/bold green]")
    elif detected_tool:
        lines.append("🔧 [bold cyan]Calling tool...[/bold cyan]")
        lines.append(f"   Tool: [bold yellow]{escape(detected_tool)}[/bold yellow]")
        if detected_files:
            lines.append(f"   Target: [dim yellow]{escape(', '.join(detected_files[:3]))}[/dim yellow]")
    elif context_kind == "consuming_file":
        lines.append("📄 [bold yellow]Processing file content...[/bold yellow]")
    else:
        lines.append("💭 [bold blue]Thinking...[/bold blue]")

    lines.append(f"   ⚡ [dim blue]{tps:.1f} t/s | Tokens: {token_count} | {elapsed:.1f}s[/dim blue]")

    if not is_done:
        lines.append("   " + "─" * 50)

    preview_max = 300
    preview = accumulated[-preview_max:] if len(accumulated) > preview_max else accumulated
    if preview and not is_done:
        preview_lines = preview.splitlines()
        trimmed_lines = []
        for line in preview_lines:
            trimmed_lines.append((line[:100] + "...") if len(line) > 100 else line)
        lines.append(f"   [dim white]{escape(chr(10).join(trimmed_lines))}[/dim white]")

    from rich.text import Text
    return Text.from_markup("\n".join(lines))


def _extract_display_path(tool_name, tool_args, result):
    """Extract a display-friendly path from tool arguments or result."""
    for key in ("path", "file_path", "directory", "dir", "url"):
        if key in tool_args:
            return str(tool_args[key])
    if "command" in tool_args:
        cmd = str(tool_args["command"])
        return cmd[:80] + "..." if len(cmd) > 80 else cmd
    if "path" in result:
        return str(result["path"])
    return "-"


def run_agent_loop(messages, model):
    """Runs the agent loop: send → parse → execute → loop.
    Mutates messages in-place to maintain the full conversation history.
    """
    context_limit = get_context_limit(model)

    while True:
        # Prepare messages for Ollama by escaping backslashes in user messages
        # to prevent Go/Jinja template rendering/tokenizer glitches with Windows paths.
        escaped_messages = []
        for msg in messages:
            if msg.get("role") == "user":
                escaped_messages.append({
                    "role": "user",
                    "content": msg.get("content", "").replace("\\", "\\\\")
                })
            else:
                escaped_messages.append(msg)

        # Detect what the model is working on: fresh thinking or processing tool output
        context_kind = _detect_context_kind(messages)

        # 1. Stream model response with live display showing real-time token stats
        content_parts = []
        token_count = 0
        detected_tool = None
        detected_files = []
        start_time = time.time()
        stream_error = None
        final_eval_count = 0
        final_eval_duration = 0
        final_prompt_eval_count = 0

        with Live(Text("Connecting..."), refresh_per_second=15, console=console) as live:
            try:
                stream = ollama.chat(model=model, messages=escaped_messages, stream=True)

                for chunk in stream:
                    token = chunk.get('message', {}).get('content', '') if isinstance(chunk, dict) else getattr(chunk.message, 'content', '')
                    if token:
                        content_parts.append(token)
                        token_count += 1

                    accumulated = ''.join(content_parts)

                    # Detect tool call in progress
                    if not detected_tool:
                        detected_tool, detected_files = _detect_tool_and_files(accumulated)

                    # Capture final stats if present
                    if isinstance(chunk, dict):
                        if chunk.get('done'):
                            final_eval_count = chunk.get('eval_count', 0) or 0
                            final_eval_duration = chunk.get('eval_duration', 0) or 0
                            final_prompt_eval_count = chunk.get('prompt_eval_count', 0) or 0
                    elif getattr(chunk, 'done', False):
                        final_eval_count = getattr(chunk, 'eval_count', 0) or 0
                        final_eval_duration = getattr(chunk, 'eval_duration', 0) or 0
                        final_prompt_eval_count = getattr(chunk, 'prompt_eval_count', 0) or 0

                    elapsed = time.time() - start_time
                    display = _build_live_display(
                        context_kind, token_count, elapsed,
                        detected_tool, detected_files, accumulated,
                        is_done=False
                    )
                    live.update(display)

                content = ''.join(content_parts)

                # Brief "done" flash
                elapsed = time.time() - start_time
                display = _build_live_display(
                    context_kind, token_count, elapsed,
                    detected_tool, detected_files, content,
                    is_done=True
                )
                live.update(display)
                time.sleep(0.15)

            except Exception as e:
                stream_error = e

        if stream_error:
            console.print(Panel(f"[red]Error during model call: {escape(str(stream_error))}[/red]", title="Error", border_style="red"))
            break

        # Build a synthetic response object for make_stats_subtitle compatibility
        class SyntheticResponse:
            pass
        synthetic = SyntheticResponse()
        synthetic.eval_count = final_eval_count or token_count
        synthetic.eval_duration = final_eval_duration or int((time.time() - start_time) * 1e9)
        synthetic.prompt_eval_count = final_prompt_eval_count
        stats_subtitle = make_stats_subtitle(synthetic, context_limit,
            "cyan" if detected_tool else "green")

        # 2. Parse model response for tool calls
        tool_call = parse_tool_call(content)

        if tool_call and isinstance(tool_call, dict) and "tool" in tool_call:
            tool_name = tool_call.get("tool")
            tool_args = tool_call.get("args", {})

            # 3. Execute the tool
            result = execute_tool(tool_name, tool_args)

            # 4. Minimal feedback
            is_error = "error" in result or result.get("returncode", 0) != 0
            if is_error:
                console.print(f"[bold red]Tool:[/bold red] {tool_name} - error")
            else:
                display_path = _extract_display_path(tool_name, tool_args, result)
                console.print(f"[bold cyan]Tool:[/bold cyan] {tool_name} - {display_path}")

            # 6. Feed the assistant response and tool result back to the messages list
            messages.append({
                "role": "assistant",
                "content": content
            })

            messages.append({
                "role": "user",
                "content": format_tool_result(result)
            })

            # Repeat the loop
        else:
            # No tool call. This is the model's final answer.
            messages.append({
                "role": "assistant",
                "content": content
            })

            # Print final answer to user with generation stats
            console.print("\n[bold green]Response:[/bold green]")
            console.print(Panel(
                content,
                border_style="green",
                title="🤖 Assistant",
                subtitle=stats_subtitle
            ))
            break
