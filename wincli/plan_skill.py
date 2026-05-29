import fnmatch
import time
import re
from pathlib import Path

import ollama
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

EXCLUDE_PATTERNS = [
    ".venv",
    ".git",
    "__pycache__",
    ".history",
    ".persist",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    "*.pyc",
    "*.pyo",
    "*.exe",
    "*.dll",
    "*.so",
    "*.pyd",
    "*.bin",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.mp3",
    "*.mp4",
    "*.wav",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.7z",
    "*.pdf",
    "WINCLI.md",
    "plans/",
]

MAX_FILE_SIZE = 100 * 1024  # 100 KB
MAX_TOTAL_CONTENT = 80 * 1024  # 80 KB total for the prompt


def _should_exclude(path, working_dir):
    """Check if a path matches any exclude pattern."""
    rel = str(path.relative_to(working_dir))

    for pattern in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(path.name, pattern):
            return True
        if fnmatch.fnmatch(rel, pattern):
            return True
        for part in path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True

    return False


def _is_text_file(path):
    """Quick check if a file is likely text."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.read(1024)
        return True
    except (UnicodeDecodeError, PermissionError, OSError):
        return False


def _slugify(text):
    """Convert text to a URL-friendly slugified filename."""
    # Convert to lowercase
    slug = text.lower()
    # Remove non-alphanumeric characters except spaces and hyphens
    slug = re.sub(r'[^\w\s-]', '', slug)
    # Replace spaces and hyphens with single hyphen
    slug = re.sub(r'[-\s]+', '-', slug)
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    # Add .md extension
    slug += '.md'
    return slug


def _scan_project_with_feedback(working_dir):
    """Scan the working directory with live visual feedback.
    Returns (files, total_size) where files is a list of (relative_path, content) tuples.
    """
    files = []
    total_size = 0
    scanned = 0
    skipped_binary = 0
    skipped_size = 0

    # Collect all candidate files first so we can show progress
    all_files = sorted(working_dir.rglob("*"))

    table = Table(title="Scanning Project", border_style="blue", box=None)
    table.add_column("Status", style="cyan", width=10)
    table.add_column("File", style="white", max_width=60)
    table.add_column("Size", style="dim", width=10, justify="right")

    latest_entries = []  # keep last N entries for display

    with Live(table, refresh_per_second=8, console=console) as live:
        for file_path in all_files:
            if not file_path.is_file():
                continue

            scanned += 1
            rel = str(file_path.relative_to(working_dir))

            if _should_exclude(file_path, working_dir):
                continue

            if not _is_text_file(file_path):
                skipped_binary += 1
                continue

            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                skipped_size += 1
                latest_entries.append(("SKIP (big)", rel, f"{size // 1024} KB"))
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                skipped_binary += 1
                continue

            if total_size + len(content) > MAX_TOTAL_CONTENT:
                keep = MAX_TOTAL_CONTENT - total_size
                files.append((rel, content[:keep]))
                latest_entries.append(("READ (cut)", rel, f"{len(content[:keep]) // 1024} KB"))
                total_size += keep
                break

            files.append((rel, content))
            total_size += len(content)
            kb = len(content) // 1024
            latest_entries.append(("READ", rel, f"{kb} KB" if kb else f"{len(content)} B"))

            # Keep only last 12 entries visible
            if len(latest_entries) > 12:
                latest_entries = latest_entries[-12:]

            # Rebuild table
            new_table = Table(title="[bold blue]Scanning Project Files[/bold blue]", border_style="blue", box=None)
            new_table.add_column("Status", style="cyan", width=10)
            new_table.add_column("File", style="white", max_width=60)
            new_table.add_column("Size", style="dim", width=10, justify="right")
            for status, fname, sz in latest_entries:
                color = "green" if "READ" in status else "yellow"
                new_table.add_row(f"[{color}]{status}[/{color}]", fname, sz)
            live.update(new_table)

    # Final summary
    console.print(Panel(
        f"[green]Scan complete.[/green]\n"
        f"  Files read: [bold cyan]{len(files)}[/bold cyan]\n"
        f"  Total content: [bold cyan]{total_size // 1024} KB[/bold cyan]\n"
        f"  Skipped (binary): {skipped_binary} | Skipped (too large): {skipped_size}",
        title="Scan Results",
        border_style="green"
    ))

    return files


def build_plan_prompt(files, wincli_content, working_dir, prompt):
    """Build the prompt for the LLM to generate a detailed action plan."""
    file_list = "\n".join(f"  - {name}" for name, _ in files)

    wincli_section = ""
    if wincli_content:
        wincli_section = f"""
BASE PROJECT CONTEXT (WINCLI.md):
The following defines the rules, architecture, conventions, and guidelines
for this project. The generated plan should follow these rules:
---
{wincli_content}
---
"""

    return f"""You are an AI agent assistant that creates detailed, structured action plans.

Task: Based on the user's prompt, generate a comprehensive plan of action.

Working directory: {working_dir}

Project files found:
{file_list}

{wincli_section}

Instructions for generating the plan:

1. **Analyze the Prompt**: Understand what the user wants to accomplish.
2. **Break Down into Steps**: Create a numbered, sequential list of actions.
3. **Add Context**: Reference relevant project files, architecture, and rules.
4. **Include Prerequisites**: List what needs to be done before starting.
5. **Add Dependencies**: Identify tools, libraries, or external systems needed.
6. **Consider Edge Cases**: Mention potential issues and how to handle them.
7. **Estimate Time**: Provide rough time estimates for each step.
8. **Format as Markdown**: Use headers, lists, code blocks, and tables for clarity.

Plan Structure:

# Plan: [Title based on user's prompt]

## Overview
[2-3 sentence summary of what this plan will accomplish]

## Prerequisites
[List of things that need to be in place before starting]

## Dependencies
- External: [APIs, services, etc.]
- Internal: [Files, modules, dependencies]

## Environment Setup
[Any configuration, installation, or environment variables needed]

## Action Steps

1. **[Step 1 Title]**
   - **Goal**: [What this step accomplishes]
   - **Action**: [Detailed description of what to do]
   - **Files to modify/create**: [List of files]
   - **Commands to run**: [Relevant commands]
   - **Expected Output**: [What result to expect]
   - **Notes**: [Any important considerations]

2. **[Step 2 Title]**
   ...

## Verification
- [How to test and validate the work]

## Rollback Plan
- [How to undo changes if needed]

## Next Steps
- [What to do after this plan is completed]

**Important**: The plan should be actionable, specific, and follow the project
conventions defined in WINCLI.md. Be concrete — an agent reading this should
know exactly what to do without further explanation.

**User's Prompt**:
{prompt}"""


def _stream_generation(model, prompt):
    """Stream the model response with live display showing tokens and content preview."""
    import queue
    import threading

    content_parts = []
    token_count = 0
    start_time = time.time()
    final_eval = 0
    final_prompt = 0
    in_reasoning = False

    q = queue.Queue()
    def worker():
        try:
            stream = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            for chunk in stream:
                q.put(("chunk", chunk))
            q.put(("done", None))
        except Exception as e:
            q.put(("error", e))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    tick = 0
    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    with Live(Text("Connecting..."), refresh_per_second=10, console=console) as live:
        try:
            running = True
            while running:
                # Drain queue
                while True:
                    try:
                        msg_type, val = q.get_nowait()
                        if msg_type == "error":
                            raise val
                        elif msg_type == "done":
                            running = False
                            if in_reasoning:
                                content_parts.append("</think>\n")
                                in_reasoning = False
                            break
                        elif msg_type == "chunk":
                            reasoning = ""
                            content = ""
                            if isinstance(val, dict):
                                msg = val.get("message", {})
                                content = msg.get("content", "") or ""
                                reasoning = msg.get("reasoning_content", "") or ""
                            else:
                                msg = getattr(val, "message", None)
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

                            token = "".join(token_parts)
                            if token:
                                content_parts.append(token)
                                token_count += 1

                            if isinstance(val, dict):
                                if val.get("done"):
                                    final_eval = val.get("done") and val.get("eval_count", 0) or 0
                                    final_prompt = val.get("done") and val.get("prompt_eval_count", 0) or 0
                            else:
                                if getattr(val, "done", False):
                                    final_eval = getattr(val, "eval_count", 0) or 0
                                    final_prompt = getattr(val, "prompt_eval_count", 0) or 0
                    except queue.Empty:
                        break

                # Rebuild display
                elapsed = time.time() - start_time
                tps = token_count / elapsed if elapsed > 0 else 0

                new_display = Text()
                new_display.append_text(Text.from_markup("[bold blue]Generating action plan with AI...[/bold blue]\n"))
                new_display.append_text(Text.from_markup(f"  Model: [cyan]{escape(model)}[/cyan] | "))

                if token_count == 0:
                    sp = SPIN[tick % len(SPIN)]
                    new_display.append_text(Text.from_markup(f"[magenta]{sp}[/magenta] [magenta]processing prompt / thinking[/magenta] | "))
                    new_display.append_text(Text.from_markup(f"[dim]{elapsed:.1f}s[/dim]\n"))
                else:
                    sp = SPIN[tick % len(SPIN)]
                    phase = "[magenta]thinking[/magenta]" if in_reasoning else "[blue]generating[/blue]"
                    new_display.append_text(Text.from_markup(f"{phase} | "))
                    new_display.append(f"Tokens: {token_count} | ")
                    new_display.append_text(Text.from_markup(f"[dim]{tps:.1f} t/s | {elapsed:.1f}s[/dim]\n"))

                new_display.append("  " + "─" * 50 + "\n\n")

                accumulated = "".join(content_parts)
                preview_lines = accumulated.splitlines()
                shown = preview_lines[-20:] if len(preview_lines) > 20 else preview_lines

                if token_count == 0:
                    new_display.append_text(Text.from_markup("[dim]Waiting for first token...[/dim]"))
                else:
                    for line in shown:
                        # Truncate long lines
                        if len(line) > 100:
                            line = line[:100] + "..."
                        new_display.append_text(Text.from_markup(f"[yellow]{escape(line)}[/yellow]\n"))

                    if len(preview_lines) > 20:
                        new_display.append_text(Text.from_markup(f"\n[dim]... ({len(preview_lines) - 20} more lines above)[/dim]"))

                live.update(new_display)
                time.sleep(0.1)
                tick += 1

        except Exception as e:
            console.print(Panel(
                f"[red]Model call failed: {escape(str(e))}[/red]",
                title="Generation Error",
                border_style="red"
            ))
            return None, 0, 0, 0

    content = "".join(content_parts)
    from agent import strip_think_blocks
    content = strip_think_blocks(content)
    elapsed = time.time() - start_time
    return content, final_prompt, final_eval or token_count, elapsed


def generate_plan(prompt, model, working_dir, wincli_content=None, session_log=None):
    """Main entry point: generate an action plan based on a user prompt.

    Args:
        prompt: The user's prompt describing what they want to accomplish.
        model: The Ollama model to use.
        working_dir: Path to the project working directory.
        wincli_content: Optional WINCLI.md content for project context.

    Returns:
        Tuple of (success: bool, plan_content: str|None, filename: str|None)
    """
    # Create plans directory if it doesn't exist
    plans_dir = working_dir / "plans"
    try:
        plans_dir.mkdir(exist_ok=True)
    except Exception as e:
        console.print(Panel(
            f"[yellow]Could not create plans directory: {escape(str(e))}[/yellow]",
            title="Plans Dir Error",
            border_style="yellow"
        ))
        return False, None, None

    console.print(Panel(
        "[bold cyan]/plan skill activated[/bold cyan]\n"
        "This will generate a detailed action plan based on your prompt\n"
        "and save it to the plans/ folder.",
        title="Plan Skill",
        border_style="cyan"
    ))

    # 1. Scan project files with live feedback
    files = _scan_project_with_feedback(working_dir)

    if not files:
        console.print(Panel(
            "[yellow]No readable files found in the project directory.[/yellow]",
            title="Plan Warning",
            border_style="yellow"
        ))
        # Still try to generate a generic plan
    
    # 2. Build prompt
    plan_prompt = build_plan_prompt(files, wincli_content, working_dir, prompt)

    # 3. Generate with streaming feedback
    console.print("")  # spacer
    res = _stream_generation(model, plan_prompt)

    if res is None or res[0] is None:
        return False, None, None
    content, prompt_tokens, gen_tokens, elapsed = res

    if not content.strip():
        console.print(Panel(
            "[red]Model returned empty response.[/red]",
            title="Generation Error",
            border_style="red"
        ))
        return False, None, None

    # 4. Save plan to file
    filename = _slugify(prompt)
    plan_path = plans_dir / filename
    
    try:
        plan_path.write_text(content.strip() + "\n", encoding="utf-8")
    except Exception as e:
        console.print(Panel(
            f"[red]Failed to save plan: {escape(str(e))}[/red]",
            title="Write Error",
            border_style="red"
        ))
        return False, None, None

    # 5. Display plan in Rich Panel
    # Truncate content for display if too long
    max_display = 5000  # chars
    display_content = content.strip()
    if len(display_content) > max_display:
        display_content = display_content[:max_display] + f"\n\n[... TRUNCATED: {len(display_content) - max_display} characters ...]"
    
    console.print(Panel(
        display_content,
        title="Generated Action Plan",
        border_style="blue",
        width=None
    ))

    tps = gen_tokens / elapsed if elapsed > 0 else 0
    if session_log:
        session_log.log_step(
            kind="assistant",
            content=f"[Generated action plan: {prompt}]",
            prompt_tokens=prompt_tokens,
            gen_tokens=gen_tokens,
            elapsed_s=elapsed
        )

    # 6. Show summary
    console.print(Panel(
        f"[green]Plan generated and saved successfully![/green]\n"
        f"  Filename: [cyan]{filename}[/cyan]\n"
        f"  Path: [cyan]{plan_path.absolute()}[/cyan]\n"
        f"  Size: [bold]{len(content):,}[/bold] chars | "
        f"Generated: [bold]{gen_tokens:,}[/bold] tokens @ [bold]{tps:.1f}[/bold] t/s | "
        f"Prompt: [bold]{prompt_tokens:,}[/bold] tokens | "
        f"Elapsed: [bold]{elapsed:.1f}s[/bold]",
        title="Plan Complete",
        border_style="green"
    ))

    return True, content, filename
