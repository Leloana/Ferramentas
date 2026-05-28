import fnmatch
import time
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


def build_init_prompt(files, working_dir):
    """Build the prompt for the LLM to generate WINCLI.md."""
    file_list = "\n".join(f"  - {name}" for name, _ in files)

    file_contents = ""
    for name, content in files:
        file_contents += f"\n### {name}\n```\n{content[:4000]}\n```\n"

    return f"""You are generating a WINCLI.md file for a project. WINCLI.md is the base
project context file — it defines the rules, architecture, conventions, and
guidelines that an AI agent should follow when working in this project.

Working directory: {working_dir}

Files found in the project:
{file_list}

Full file contents:
{file_contents}

Based on the project files above, create a comprehensive WINCLI.md file.
Follow this structure:

1. **Project Overview** — What this project does, its purpose, and tech stack
2. **Architecture** — How the code is organized, main components, data flow
3. **Conventions** — Code style, naming patterns, file organization rules
4. **Commands** — How to run, build, test the project
5. **Key Files** — What each important file does
6. **Rules for Agents** — Specific instructions an AI agent should follow when editing this project

Write the WINCLI.md in clear markdown. Be specific and actionable — an AI agent
reading this should know exactly how to work in this project. Do NOT include generic
advice or placeholder text. Only output the WINCLI.md content, no preamble."""


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
                new_display.append_text(Text.from_markup("[bold blue]Generating WINCLI.md with AI...[/bold blue]\n"))
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


def generate_wincli(working_dir, model, session_log=None):
    """Main entry point: scan project, generate WINCLI.md via Ollama, write result."""

    console.print(Panel(
        "[bold cyan]/init skill activated[/bold cyan]\n"
        "This will scan all project files and generate a WINCLI.md\n"
        "with rules, architecture, and guidelines for AI agents.",
        title="Init Skill",
        border_style="cyan"
    ))

    # 1. Scan project files with live feedback
    files = _scan_project_with_feedback(working_dir)

    if not files:
        console.print(Panel(
            "[yellow]No readable files found in the project directory.[/yellow]",
            title="Init Warning",
            border_style="yellow"
        ))
        return False

    # 2. Build prompt
    prompt = build_init_prompt(files, working_dir)

    # 3. Generate with streaming feedback
    console.print("")  # spacer
    res = _stream_generation(model, prompt)

    if res is None or res[0] is None:
        return False
    content, prompt_tokens, gen_tokens, elapsed = res

    if not content.strip():
        console.print(Panel(
            "[red]Model returned empty response.[/red]",
            title="Generation Error",
            border_style="red"
        ))
        return False

    # 4. Write WINCLI.md
    wincli_path = working_dir / "WINCLI.md"
    try:
        wincli_path.write_text(content.strip() + "\n", encoding="utf-8")
    except Exception as e:
        console.print(Panel(
            f"[red]Failed to write WINCLI.md: {escape(str(e))}[/red]",
            title="Write Error",
            border_style="red"
        ))
        return False

    tps = gen_tokens / elapsed if elapsed > 0 else 0
    if session_log:
        session_log.log_step(
            kind="assistant",
            content="[Generated WINCLI.md]",
            prompt_tokens=prompt_tokens,
            gen_tokens=gen_tokens,
            elapsed_s=elapsed
        )

    # 5. Show final summary
    console.print(Panel(
        f"[green]WINCLI.md generated successfully![/green]\n"
        f"  Path: [cyan]{wincli_path}[/cyan]\n"
        f"  Size: [bold]{len(content):,}[/bold] chars | "
        f"Generated: [bold]{gen_tokens:,}[/bold] tokens @ [bold]{tps:.1f}[/bold] t/s | "
        f"Prompt: [bold]{prompt_tokens:,}[/bold] tokens | "
        f"Elapsed: [bold]{elapsed:.1f}s[/bold]\n\n"
        f"[dim]The agent will now load this file as base project context on future sessions.[/dim]",
        title="Init Complete",
        border_style="green"
    ))
    return True
