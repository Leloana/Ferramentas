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
    content_parts = []
    token_count = 0
    start_time = time.time()
    detected_tool = None

    display = Text()
    display.append("[bold blue]Generating WINCLI.md with AI...[/bold blue]\n")
    display.append(f"  Model: [cyan]{model}[/cyan]\n")
    display.append(f"  Prompt size: [dim]{len(prompt) // 1024} KB[/dim]\n")
    display.append("  " + "─" * 50 + "\n\n")
    display.append("[dim]Waiting for response...[/dim]")

    with Live(display, refresh_per_second=15, console=console) as live:
        try:
            stream = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )

            for chunk in stream:
                token = (
                    chunk.get("message", {}).get("content", "")
                    if isinstance(chunk, dict)
                    else getattr(chunk.message, "content", "")
                )
                if token:
                    content_parts.append(token)
                    token_count += 1

                accumulated = "".join(content_parts)
                elapsed = time.time() - start_time
                tps = token_count / elapsed if elapsed > 0 else 0

                # Rebuild display
                new_display = Text()
                new_display.append("[bold blue]Generating WINCLI.md with AI...[/bold blue]\n")
                new_display.append(f"  Model: [cyan]{model}[/cyan] | ")
                new_display.append(f"Tokens: {token_count} | ")
                new_display.append(f"[dim]{tps:.1f} t/s | {elapsed:.1f}s[/dim]\n")
                new_display.append("  " + "─" * 50 + "\n\n")

                # Show last N lines of generated content
                preview_lines = accumulated.splitlines()
                shown = preview_lines[-20:] if len(preview_lines) > 20 else preview_lines
                for line in shown:
                    # Truncate long lines
                    if len(line) > 100:
                        line = line[:100] + "..."
                    new_display.append(f"[yellow]{line}[/yellow]\n")

                if len(preview_lines) > 20:
                    new_display.append(f"\n[dim]... ({len(preview_lines) - 20} more lines above)[/dim]")

                live.update(new_display)

        except Exception as e:
            console.print(Panel(
                f"[red]Model call failed: {escape(str(e))}[/red]",
                title="Generation Error",
                border_style="red"
            ))
            return None, 0, 0, 0

    content = "".join(content_parts)
    elapsed = time.time() - start_time
    return content, token_count, elapsed, token_count / elapsed if elapsed > 0 else 0


def generate_wincli(working_dir, model):
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
    content, token_count, elapsed, tps = _stream_generation(model, prompt)

    if content is None:
        return False

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

    # 5. Show final summary
    console.print(Panel(
        f"[green]WINCLI.md generated successfully![/green]\n"
        f"  Path: [cyan]{wincli_path}[/cyan]\n"
        f"  Size: [bold]{len(content):,}[/bold] chars | "
        f"Generated: [bold]{token_count:,}[/bold] tokens @ [bold]{tps:.1f}[/bold] t/s | "
        f"Elapsed: [bold]{elapsed:.1f}s[/bold]\n\n"
        f"[dim]The agent will now load this file as base project context on future sessions.[/dim]",
        title="Init Complete",
        border_style="green"
    ))
    return True
