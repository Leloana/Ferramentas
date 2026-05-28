# WINCLI.md

# Agentic CLI Project Context

## 1. Project Overview

This project is a Windows-native Command Line Interface (CLI) that acts as an agent for interacting with a local Ollama instance. It allows users to execute shell commands, read/write files, list directories, search code, and perform HTTP requests, all managed by an LLM.

**Purpose**: Provide a seamless, terminal-based interface for AI agents to manipulate the file system and run system commands under the supervision of a local language model.

**Tech Stack**:
- **Language**: Python 3.12+
- **Core Logic**: Pure Python (no LangChain, no OpenAI)
- **LLM Connection**: Ollama API (`ollama` package)
- **Terminal UI**: Rich (`rich`) for formatting and `prompt_toolkit` for input history
- **File Paths**: `pathlib2` (primary) / `pathlib` (standard)
- **HTTP**: `requests`

**Working Directory**: `C:\Users\mf827\Documents\Ferramentas\agentic_cli` (or wherever the project root is cloned).

---

## 2. Architecture

The application follows a modular structure centered around a main CLI loop.

### Data Flow
1.  **Startup**: `main.py` checks for Ollama connection, lists available models, and initializes the session.
2.  **Loop**: The agent loop (inside `agent.py`) runs continuously:
    - Sends current history to Ollama.
    - Parses LLM response for JSON tool calls.
    - Executes tools via `tools.py`.
    - Formats tool output (`agent.py`) and feeds back into the conversation.
3.  **Context**: `WINCLI.md` is loaded into the LLM prompt to ground the agent in the project's rules.
4.  **Initialization**: `init_skill.py` scans the project for existing files and can regenerate `WINCLI.md` if needed via the `/init` command.

### Components
-   **`main.py`**: Handles CLI entry point, signal handling (Ctrl+C), Ollama connection verification, model selection UI.
-   **`agent.py`**: Core logic for parsing tool JSON, formatting tool results for the LLM, tracking token usage (`get_context_limit`, `make_stats_subtitle`).
-   **`tools.py`**: Registry of executable tools (shell, file, HTTP).
-   **`init_skill.py`**: Scans working directory, excludes sensitive files (`.git`, `.venv`), and builds prompts for context generation.
-   **`setup.bat` / `run.bat`**: Batch scripts to manage the Python virtual environment and launch the app.

---

## 3. Conventions

### Code Style
-   **Imports**: Standardize import order (stdlib -> `pathlib2` -> third-party).
-   **Paths**: Use `pathlib2.Path` (imported as `Path`) for file operations, specifically in `tools.py`.
-   **Output**: Use `rich` console for all terminal output (panels, status bars, spinners).
-   **Error Handling**: Use try/except blocks in `agent.py` and `tools.py` to catch and format exceptions into messages for the LLM.

### Tool Calling Format
The LLM must output tool requests in the following JSON block wrapped in markdown code fences:
```json
{
  "tool": "tool_name",
  "args": {
    "param": "value"
  }
}
```
The agent loop expects this specific format to parse and execute.

### Environment Management
-   Always activate the virtual environment defined in `.venv`.
-   Dependencies are managed via `requirements.txt` inside `.venv`.
-   Use `setup.bat` to create/refresh the environment.
-   Do not install packages directly into the system Python.

### File Exclusions
When scanning the project or reading files, ignore:
-   `.venv`, `.git`, `__pycache__`, `.history`
-   Binary files (images, media, zip, etc.)
-   `WINCLI.md` (to avoid infinite loops during init)
-   Files larger than 100 KB (max size for scanning).

---

## 4. Commands

### CLI Commands (Inside `main.py` Loop)
Type these commands while the CLI is running:

| Command | Description |
| :--- | :--- |
| `/init` | Scans the project files and regenerates `WINCLI.md`. |
| `/exit` | Closes the CLI (or type `quit`). |
| `list_dir <path>` | Lists files in a directory (use tool `list_dir`). |
| `cat <path>` | Read a file (use tool `read_file`). |
| `edit <path>` | Edit/create a file (use tool `write_file`). |
| `cmd <command>` | Run shell command (use tool `run_command`). |
| `search <file> <str>` | Search file for string (use tool `search_file`). |

### System Commands (PowerShell)
| Command | Description |
| :--- | :--- |
| `setup.bat` | Create venv and install dependencies. |
| `run.bat` | Launch the CLI agent. |
| `ollama list` | Check available models. |
| `ollama pull <model>` | Pull a model before use. |

### Build/Run
-   **Build**: Not applicable (interpreted). Run `setup.bat` once.
-   **Test**: Run `run.bat` and interact with the CLI (e.g., `list_dir .`).

---

## 5. Key Files

### `main.py`
-   **Role**: Entry point.
-   **Function**: Sets up signal handlers (`on_ctrl_c`), connects to Ollama, displays the model selection menu, starts the agent loop (`run_agent_loop`).
-   **Key Logic**: Imports `from agent import run_agent_loop` and `from init_skill import generate_wincli`.

### `agent.py`
-   **Role**: Agent loop execution and response formatting.
-   **Function**: `parse_tool_call` extracts JSON from LLM responses. `execute_tool` dispatches to `tools.py`. `format_tool_result` converts tool output into the LLM-readable format. Tracks token consumption vs. context limit.
-   **Key Logic**: Relies on `tools` module for execution.

### `tools.py`
-   **Role**: Tool implementations.
-   **Function**: Defines the 6 tools: `run_command` (shell), `read_file` (file read), `write_file` (file write), `list_dir` (ls), `search_file` (grep), `http_get` (fetch).
-   **Key Logic**: Uses `subprocess` for shell, `pathlib2.Path` for IO, `requests` for HTTP.

### `init_skill.py`
-   **Role**: Context management.
-   **Function**: `scan_project` filters files based on `EXCLUDE_PATTERNS`. `build_init_prompt` constructs the markdown text for `WINCLI.md` based on project contents.
-   **Key Logic**: Respects `MAX_FILE_SIZE` (100KB) and `MAX_TOTAL_CONTENT` (80KB) to avoid context overflow.

### `tools.py` / `requirements.txt`
-   **Role**: Dependencies and implementation details.
-   **Function**: `requirements.txt` pins versions (`ollama`, `rich`, `prompt_toolkit`, `pathlib2`, `requests`).

---

## 6. Rules for Agents

When working in this project, follow these specific instructions to ensure stability and correctness:

### 1. Context Loading
-   **Always Load WINCLI.md**: On startup, check if `WINCLI.md` exists at the root. If it does, read its content into the LLM context (via `load_wincli_context`).
-   **Regenerate if Needed**: If `WINCLI.md` is missing or outdated, instruct the user to run `/init`.
-   **Exclusion List**: Never include hidden folders (`.git`, `.venv`) or binary assets in the context payload to save tokens.

### 2. Tool Usage Safety
-   **Shell Execution**: `run_command` executes `powershell.exe`. Do not pass commands that modify the registry or require admin privileges unless explicitly requested.
-   **File Writing**: Before using `write_file`, verify the path is within the project root to prevent accidental OS modifications.
-   **File Reading**: If a file is unreadable (binary or locked), return a clean error message to the user.
-   **Token Limits**: Monitor token consumption via `get_context_limit`. If approaching the Ollama limit (`num_ctx`), summarize previous history before continuing.

### 3. Error Handling
-   **JSON Parsing**: If `parse_tool_call` fails (invalid JSON in response), treat it as a natural language response and format it for the user.
-   **Subprocess Errors**: If `run_command` fails, print `stderr` to the user before retrying.
-   **Ollama Disconnection**: If `ollama.list` fails, abort gracefully and instruct the user to check `localhost:11434`.

### 4. File Operations
-   **Encoding**: Always use `encoding="utf-8"` when reading/writing text files (e.g., `read_file`, `write_file`).
-   **Overwriting**: `write_file` overwrites existing files. Confirm user intent if the path is critical.
-   **Truncation**: If file contents exceed token limits during `scan_project`, truncate content and append a `[... TRUNCATED ...]` marker.

### 5. Environment Handling
-   **Virtual Env**: Never install dependencies globally. Always use `.venv\Scripts\activate` or ensure `run.bat` activates it first.
-   **Path Resolution**: Work relative to the project root (`Path.cwd()`). Do not assume absolute paths unless passed in args.
-   **Batch Scripts**: If the user requests setup, remind them to run `setup.bat` before running `run.bat`.

### 6. User Feedback
-   **Rich Panels**: Use `rich.console` for all status updates (e.g., "Scanning project...", "Model selected: qwen3.5").
-   **Live Updates**: When scanning large directories, provide a live progress indicator or summary if `Live` context is available.
-   **Clear Errors**: Avoid printing raw Python traces to the user; convert exceptions to human-readable messages (e.g., "File not found" instead of `FileNotFoundError`).
