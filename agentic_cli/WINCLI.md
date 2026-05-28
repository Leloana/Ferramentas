# WINCLI.md: Windows Agentic CLI Context

This document serves as the definitive guide, architecture map, and set of rules for working on the Windows Agentic CLI project. It defines the behavior, conventions, and structure that all AI agents must adhere to maintain code quality, security, and functional consistency.

---

## 📂 1. Project Overview

**Project Goal:** To build a highly capable, stateful Command Line Interface (CLI) that functions as an agentic wrapper around a local LLM (Ollama). The CLI allows a user to instruct the system using natural language prompts, and the agent interprets this intent, uses defined tools (like file I/O, system commands, network requests) to execute steps, persists the state, and iteratively refines its action until a final outcome is achieved.

**Target Environment:** Windows OS (Windows PowerShell commands are the standard for `run_command`).

**Core Technology Stack:**
*   **Language:** Python 3.x
*   **LLM Integration:** Ollama (local API client)
*   **UI/Presentation:** Rich (terminal formatting)
*   **CLI Input:** Prompt Toolkit (history management)
*   **State Management:** Python `dataclasses` and file persistence (`json` logging).

**Agentic Loop Functionality:** The system operates on a structured loop: **User Prompt $\rightarrow$ Agent Thought $\rightarrow$ Tool Call (JSON) $\rightarrow$ Tool Execution $\rightarrow$ Tool Result $\rightarrow$ LLM Synthesis $\rightarrow$ Final Answer/Next Tool Call.**

---

## 🏗️ 2. Architecture

The system is structured around modularity and state separation, preventing monolithic functions and ensuring that side effects (logging, state changes) are atomic and predictable.

### 2.1 Core Components & Data Flow

1.  **Input & Context (`main.py`):** The `main.py` file is the primary entry point. It handles initial startup, command parsing (slash commands like `/init`, `/mode`), and constructs the system prompt that defines the toolset and project context.
2.  **State Management (`modes.py`, `persist.py`):**
    *   `modes.py` tracks session permissions and operating modes (`SessionState`). It acts as the primary gatekeeper, determining if an action is allowed before execution.
    *   `persist.py` manages the session history (`.persist/<id>.json`). Every turn and tool interaction updates the log, ensuring the LLM can always reference the complete, structured conversational history.
3.  **Agent Brain (`agent.py`):** This component orchestrates the agent's thinking process.
    *   It manages the loop structure.
    *   It handles LLM output parsing, specifically extracting tool call JSON blocks.
    *   It executes the tool via `execute_tool` after passing through the gate check in `modes.py`.
    *   It implements advanced features like the Circuit Breaker (detecting repeated tool failures).
4.  **Tool Dispatcher (`agent.py` $\rightarrow$ `tools/`):** The `_dispatch_tool` function resolves the tool name provided by the LLM to an actual callable Python function. This supports both `CORE_TOOLS` and dynamically added skills (via `extra_tools`).
5.  **Project Context (`init_skill.py`):** Responsible for scanning the working directory. It reads all accessible text files, respecting size limits (`MAX_TOTAL_CONTENT`), and embedding the result into the context provided to the LLM.

### 2.2 Tool Call Format

The LLM must *only* return tool calls in a specific JSON format:

```json
{"tool": "<tool_name>", "args": {"param1": "<value1>", "param2": "<value2>"}}
```

Any thought process or pre-amble must be wrapped in `` tags, which are stripped by `agent.py` for clean context display but are used by the agent's internal reasoning.

---

## 🎨 3. Conventions

### 3.1 Coding Standards

*   **Readability:** Python standard library practices (PEP 8). Use type hinting extensively.
*   **Modularity:** Separate concerns into distinct files. `agent.py` must handle orchestration, while `tools/` handles execution logic.
*   **Immutability:** Session state updates (tokens, time) must be handled by dedicated methods (e.g., `SessionLog.log_step`).
*   **Error Handling:** All external API calls (file I/O, network) must be wrapped in `try...except` blocks, providing structured output (e.g., `{"error": str(e)}`) to the LLM.

### 3.2 File Structure & Naming

*   **`*.py` files:** Must contain single, focused functionalities (e.g., `modes.py` handles *only* state and permission logic).
*   **Tools:** All primary tools (e.g., `run_command`, `read_file`) are placed in or imported from the `tools` module structure.
*   **Logging:** Persistence logs must reside exclusively in the `.persist/` directory and follow the strict JSON schema defined in `persist.py`.

### 3.3 Security and Safety (The Gatekeeper)

All actions that modify the system state (`write_file`, `patch_file`, `run_command`) *must* pass through the `modes.py` gatekeeper function (`gate_tool`).

1.  The agent must first propose the action.
2.  The `gate_tool` function verifies permission based on `SessionState`.
3.  If required, the user sees a rich `_diff_preview` panel before execution.
4.  The tool executes only if the gate passes.

---

## 🚀 4. Commands & Usage

### 4.1 Setup and Execution

1.  **Environment Setup:** The agent must run within a virtual environment defined by the system setup scripts (`setup.bat` $\rightarrow$ activate $\rightarrow$ run `main.py`).
2.  **Initial Context Load:** The agent must call `/init` explicitly at startup to generate or update `WINCLI.md`, ensuring the current state of the codebase is always available as context.

### 4.2 Internal CLI Commands (Slash Commands)

| Command | Purpose | Functionality |
| :--- | :--- | :--- |
| `/init` | **Initialize Context** | Regenerates or refreshes `WINCLI.md` using `init_skill.py`. The output is critical for the agent to maintain project awareness. |
| `/mode [args]` | **Manage Operational Mode** | Sets `op_mode` (normal/plan/debug) or `perm_mode` (bypass/ask_edits/ask_all). This immediately affects the agent's tool usage restrictions and prompting style. |
| `/context` | **Show State** | Displays a panel summarizing current token usage, session ID, and active modes (`SessionState`). |
| `/skill <name> [args]` | **Execute Custom Skill** | Invokes specialized, user-defined capabilities (e.g., `generate_plan`). |
| `/plan <prompt>` | **Plan Generation Shortcut** | Executes `generate_plan` skill. Creates a structured plan, saves it to `plans/<slug>.md`, and adds it to the history. |
| `/reflect [hint]` | **Reflection Cycle** | Executes the `reflect` skill. Used for self-correction, especially after a tool failure or ambiguous result. |

---

## 💾 5. Key Files Documentation

### `main.py`
*   **Role:** Bootstrap and CLI handler.
*   **Responsibilities:**
    *   Loading and calling the `load_wincli_context` function.
    *   Building the massive system prompt (`build_system_prompt`) by injecting the working directory structure and all tool definitions (including `ACTIVE_PATCH` variants).
    *   Rendering the prompt based on `SessionState` and token usage (`render_prompt`).
    *   Delegating the main loop execution to `run_agent_loop` in `agent.py`.

### `agent.py`
*   **Role:** The agentic engine and loop controller.
*   **Responsibilities:**
    *   **Loop Control:** Implements the core loop logic.
    *   **Parsing:** Uses regex (`THINK_RE`, `parse_tool_call`) to reliably extract thoughts and tool calls from the LLM's text response.
    *   **Execution:** Calls `_dispatch_tool` $\rightarrow$ `execute_tool`.
    *   **Failure Handling:** Implements the Circuit Breaker and calls `reflect` upon detection of 3 consecutive failures for the same tool/args hash.
    *   **Logging:** Calls `persist.log_step` after *every* state change.

### `modes.py`
*   **Role:** Security and operational state management.
*   **Responsibilities:**
    *   Maintaining the `SessionState` object (`op_mode`, `perm_mode`).
    *   `_needs_gate()`: Determining if a tool call requires user permission based on the current mode.
    *   `gate_tool()`: The official permission check function. If the tool needs gating, this function controls execution flow and records "always allow" grants into `SessionState`.
    *   `_diff_preview()`: Provides rich, actionable previews of file changes (diffs) or command execution context.

### `persist.py`
*   **Role:** Guaranteed state persistence and historical tracking.
*   **Responsibilities:**
    *   Initializing and managing the `SessionLog` object.
    *   Providing the `session_totals()` method to calculate token consumption across all turns.
    *   The `log_step()` method must be the single point of truth for updating all session metrics (tokens, elapsed time, tool call/result).

### `init_skill.py`
*   **Role:** Project environment context scanner.
*   **Responsibilities:**
    *   Recursively walking the `working_dir` (`rglob`).
    *   Implementing exclusion logic (`_should_exclude`) to prevent reading binary or irrelevant files.
    *   Enforcing size limits (`MAX_FILE_SIZE`, `MAX_TOTAL_CONTENT`) to prevent context window overflow.
    *   Providing rich, live visual feedback to the user during scanning.

---

## ⚠️ 6. Rules for Agents (AI Agent Guidelines)

1.  **Contextual Consistency is Paramount:** Never assume the agent has knowledge of a file or piece of context that was not passed via `WINCLI.md` or explicitly loaded by `/init`.
2.  **Tool Call Precision:** When generating code or suggesting agent actions, always mimic the exact JSON structure required by the LLM tool parser. Do not include introductory text outside the JSON block.
3.  **Error Handling Simulation:** When troubleshooting tool failures (e.g., `FileNotFoundError`), prioritize returning a detailed, actionable `hint` (using the logic in `agent.py: _error_hint`) rather than merely passing the raw Python traceback to the LLM.
4.  **Permission First:** If implementing any new tool or modifying existing tools, always verify that the tool execution *must* be wrapped by or consulted with `modes.py` to adhere to permission gating.
5.  **Testing Strategy:** All modifications to tool functionality (in `tools/`) or state management (in `modes.py`, `persist.py`) must be accompanied by dedicated unit tests demonstrating both the success case and the failure/permission denial case.
6.  **Data Integrity:** When modifying data structures, always use the provided `SessionLog` methods (`log_step`) to ensure token counting and session totals are accurately updated. Do not manipulate the underlying `self.data` dictionary directly.
