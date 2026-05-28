import sys
import signal
from pathlib import Path

import ollama
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory

import tools
from agent import run_agent_loop
from init_skill import generate_wincli
from plan_skill import generate_plan

console = Console()


def on_ctrl_c(signum, frame):
    console.print("\n[yellow]Interrupted. Exiting...[/yellow]")
    sys.exit(0)


# Set up Ctrl+C handler
signal.signal(signal.SIGINT, on_ctrl_c)


def load_wincli_context(working_dir):
    """Search for WINCLI.md in the working directory and return its content.
    WINCLI.md serves as the base project context, similar to CLAUDE.md for Claude Code.
    """
    wincli_path = working_dir / "WINCLI.md"
    if wincli_path.exists():
        try:
            content = wincli_path.read_text(encoding="utf-8")
            return content, True
        except Exception:
            return None, False
    return None, False


def show_tool_definitions(wincli_loaded):
    tool_descriptions = [
        ("run_command", "Execute a Windows PowerShell command (e.g., Get-ChildItem, Get-NetIPAddress)"),
        ("read_file", "Read the contents of a file (including WINCLI.md at startup)"),
        ("write_file", "Write or overwrite a new file (use patch_file for edits)"),
        ("patch_file", "Patch a file by replacing old_str with new_str"),
        ("list_dir", "List files and folders in a directory"),
        ("search_file", "Search for a string in a file"),
        ("http_get", "Make an HTTP GET request"),
    ]

    description_lines = ["[bold yellow]Available Agentic Tools:[/bold yellow]\n"]
    for name, desc in tool_descriptions:
        description_lines.append(f"  • [cyan]{name}[/cyan]: {desc}")

    description_lines.append("")
    description_lines.append("[bold yellow]Commands:[/bold yellow]")
    description_lines.append("  • [cyan]/init[/cyan] — Scan the project and generate WINCLI.md automatically")
    description_lines.append("  • [cyan]exit[/cyan] / [cyan]quit[/cyan] — Close the CLI")
    description_lines.append("")
    if wincli_loaded:
        description_lines.append("[bold green]WINCLI.md[/bold green] found and loaded as base project context.")
    else:
        description_lines.append("[dim]No WINCLI.md found. Type [cyan]/init[/cyan] to generate one, or create it manually.[/dim]")

    return "\n".join(description_lines)


def main():
    console.print(Panel.fit("[bold magenta]Agentic CLI - Powered by Ollama[/bold magenta]", style="bold magenta"))

    # 0. Resolve working directory — this is the project root the agent operates in
    working_dir = Path.cwd().resolve()
    console.print(Panel(
        f"[dim]Working directory:[/dim] [bold cyan]{working_dir}[/bold cyan]",
        title="Project Root",
        border_style="blue"
    ))

    # 1. Connect and verify Ollama connection
    with console.status("[bold blue]Connecting to local Ollama instance...", spinner="dots"):
        try:
            models_data = ollama.list()
        except Exception as e:
            console.print(Panel(
                f"[red]Failed to connect to Ollama at http://localhost:11434.\nError: {escape(str(e))}\n\nPlease ensure Ollama is running.[/red]",
                title="❌ Connection Error",
                border_style="red"
            ))
            sys.exit(1)
            
    available = [m.get('name', m.get('model', '')) for m in models_data.get('models', [])]
    available = [name for name in available if name] # Filter empty names
    
    if not available:
        console.print(Panel(
            "[yellow]Connected to Ollama, but no models were found.\nRun 'ollama pull <model_name>' first.[/yellow]",
            title="⚠️ No Models Found",
            border_style="yellow"
        ))
        sys.exit(1)

    # 2. Show connection status and model menu
    console.print(Panel(
        "[green]Successfully connected to Ollama![/green]",
        title="Status",
        border_style="green"
    ))
    
    console.print("[bold yellow]Available Models:[/bold yellow]")
    for i, model in enumerate(available):
        console.print(f"  [cyan]{i+1}[/cyan]. {model}")
    console.print("")

    # 3. Model selection
    selected_index_str = Prompt.ask(
        "Select a model (enter number)",
        choices=[str(i+1) for i in range(len(available))],
        default="1"
    )
    selected_model = available[int(selected_index_str) - 1]
    
    # Load WINCLI.md as base project context (similar to CLAUDE.md)
    wincli_content, wincli_loaded = load_wincli_context(working_dir)

    console.print(Panel(
        f"Selected model: [bold green]{selected_model}[/bold green]\n"
        "Ready for commands. Type [cyan]exit[/cyan] or [cyan]quit[/cyan] to leave.\n"
        "Type [cyan]/init[/cyan] to scan the project and generate WINCLI.md.",
        title="Ready",
        border_style="green"
    ))

    console.print(Panel(show_tool_definitions(wincli_loaded), border_style="blue"))

    # Build project context section from WINCLI.md
    wincli_section = ""
    if wincli_loaded:
        wincli_section = f"""
BASE PROJECT CONTEXT (WINCLI.md):
The following is the project's WINCLI.md file, which defines the rules, architecture,
and guidelines for this project. Always follow these instructions when working here:
---
{wincli_content}
---
"""

    # System prompt instructing the model on tool usage
    system_prompt = f"""You are an agentic assistant with access to the following tools.

WORKING DIRECTORY: {working_dir}
All file paths are relative to this directory unless specified as absolute paths.
{wincli_section}
Available tools:
- run_command: Execute a Windows PowerShell command. Arguments: {{"command": "<powershell_command_string>"}}
- read_file: Read the contents of a file. Arguments: {{"path": "<file_path>"}}
- write_file: Write a new file from scratch. Arguments: {{"path": "<file_path>", "content": "<file_content>"}}
- patch_file: Replace the first occurrence of old_str with new_str in an existing file. Arguments: {{"path": "<file_path>", "old_str": "<exact_text_to_replace>", "new_str": "<replacement_text>"}}
- list_dir: List files and folders in a directory. Arguments: {{"path": "<dir_path>"}}
- search_file: Search for a string in a file. Arguments: {{"path": "<file_path>", "query": "<search_query>"}}
- http_get: Make an HTTP GET request. Arguments: {{"url": "<url_string>"}}

To use a tool, you MUST output a JSON block wrapped in triple backticks:
```json
{{"tool": "<tool_name>", "args": {{<param>: "<value>"}}}}
```

CRITICAL:
1. ONLY call one tool at a time.
2. After calling a tool, wait for the user to provide the result.
3. Keep calling tools iteratively until you have gathered enough information to give a final answer.
4. When you have the final answer, write it directly to the user WITHOUT using the tool call JSON block.
5. All commands executed via `run_command` run in Windows PowerShell. Always write commands in valid PowerShell syntax (e.g., use `Get-ChildItem` instead of `dir`, `Get-Content` instead of `type`).
6. If a WINCLI.md context is provided above, always follow its rules and guidelines. If no WINCLI.md was loaded, you may suggest the user create one for better project-specific guidance.
7. When completing a task, respond with a brief summary only: list created/modified/deleted files and commands run. Do NOT explain unless the user asks. Example: "Created: file1.txt | Modified: file2.py | Ran: <cmd> → OK"
8. When modifying existing files, always use patch_file instead of write_file. Only use write_file for creating new files from scratch.
"""

    conversation_history = [{
        "role": "system",
        "content": system_prompt,
    }]
    
    # 4. Interactive CLI loop with prompt_toolkit history
    history = FileHistory('.history')
    
    while True:
        try:
            user_input = prompt('\n> ', history=history)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Exiting...[/yellow]")
            sys.exit(0)
        except EOFError:
            console.print("\n[yellow]Goodbye![/yellow]")
            sys.exit(0)
            
        user_input = user_input.strip()
        if not user_input:
            continue
            
        if user_input.lower() in ("exit", "quit"):
            console.print("[yellow]Goodbye![/yellow]")
            sys.exit(0)

        if user_input.lower().startswith("/init"):
            console.print("[bold cyan]Activating /init skill — scanning project and generating WINCLI.md...[/bold cyan]\n")
            try:
                success = generate_wincli(working_dir, selected_model)
                if success:
                    # Reload WINCLI.md into the current session context
                    wincli_content, wincli_loaded = load_wincli_context(working_dir)
                    if wincli_loaded:
                        conversation_history.append({
                            "role": "user",
                            "content": "[SYSTEM] WINCLI.md has been generated and loaded. Its content is now the base project context for all future work in this session.",
                        })
                else:
                    console.print("[yellow]/init did not complete successfully.[/yellow]")
            except Exception as e:
                console.print(Panel(f"[red]Init failed: {escape(str(e))}[/red]", title="Init Error", border_style="red"))
            continue
            
        conversation_history.append({
            "role": "user",
            "content": user_input,
        })
        
        try:
            run_agent_loop(conversation_history, selected_model)
        except Exception as e:
            console.print(Panel(f"[red]Error during execution: {escape(str(e))}[/red]", title="❌ Error", border_style="red"))


if __name__ == "__main__":
    main()
