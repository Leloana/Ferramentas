# WINCLI.md: Windows Agentic CLI Project Guidelines

This document defines the rules, architecture, conventions, and guidelines for working within the `agentic_cli` project. Adherence to these standards is mandatory for all development and modification tasks.

***

## 📚 1. Project Overview

**Project Name:** Windows Agentic CLI (WINCLI)
**Purpose:** To build a sophisticated, stateful, and highly constrained command-line interface that allows a Large Language Model (LLM), specifically connected to a local Ollama instance, to interact with the Windows filesystem and execute PowerShell commands programmatically.

**Goal:** The agent must act as a skilled, permission-aware, and contextual developer working within a limited, well-defined sandbox environment. The system must prioritize auditability, state management, and adherence to security boundaries.

**Tech Stack:**
*   **Language:** Python
*   **CLI Framework:** Rich (for rich, modern terminal output)
*   **LLM Backend:** Ollama
*   **Operating System Target:** Windows (All command execution defaults to PowerShell).

***

## 🏛️ 2. Architecture

The system is designed around a tight feedback loop: **Agent $\rightarrow$ Tool $\rightarrow$ Result $\rightarrow$ Agent**. State and permissions are layered on top of this core loop.

### A. Core Components
1.  **Agent Loop (`agent.py`):** The execution engine. This module controls the flow: receiving model output, parsing potential tool calls, enforcing state changes (circuit breakers, permission gating), executing the tool, and re-injecting the result back into the LLM context.
2.  **State Management (`modes.py`):** Determines *if* an action is allowed and *how* the agent thinks. It enforces the `op_mode` (process/planning logic) and `perm_mode` (tool/file system access security).
3.  **Persistence Layer (`persist.py`):** Provides session memory. Every interaction, tool call, and token count is logged to a unique JSON file (`.persist/`) to ensure complete auditability and the ability to resume work.
4.  **Context Layer (`init_skill.py`):** Responsible for scanning the working directory. It reads file contents and directory structure, respecting `MAX_FILE_SIZE` and `MAX_TOTAL_CONTENT` limits, to build the comprehensive context given to the LLM.
5.  **Interaction Layer (`tools`):** Houses all callable functions (`read_file`, `write_file`, `run_command`, etc.) that the LLM can invoke. These functions must handle potential errors gracefully and return structured output for the LLM.
6.  **Entry Point (`main.py`):** Initializes the CLI, handles command arguments (`/init`, `/mode`), and coordinates the session setup before passing control to `agent.py`.

### B. Data Flow
1.  **Startup:** `main.py` calls `init_skill.py` $\rightarrow$ Scanner collects files $\rightarrow$ Context is built $\rightarrow$ System Prompt is created $\rightarrow$ `agent.py` starts the loop.
2.  **Agent Action:** LLM outputs a tool call JSON block $\rightarrow$ `agent.py` intercepts and parses it $\rightarrow$ `agent.py` calls `modes.py` (for gating) $\rightarrow$ `agent.py` executes the function in `tools` $\rightarrow$ The result is returned to `agent.py` $\rightarrow$ Result is packaged and sent back to the LLM for the next turn.
3.  **State Update:** In every step, `persist.py` updates the session log.

***

## 📐 3. Conventions

### A. Code Style
*   **PEP 8 Compliance:** All Python code must adhere to standard PEP 8 conventions (naming, spacing, imports).
*   **Type Hinting:** Use comprehensive type hinting for all function signatures (`def func(arg: Type) -> ReturnType:`).
*   **Docstrings:** Every public function and class must have a docstring explaining its purpose, parameters (`:param:`), and return value (`:return:`).

### B. Naming Conventions
*   **Files/Modules:** Use lowercase snake\_case (e.g., `plan_skill.py`, `session_log.py`).
*   **Classes:** Use PascalCase (e.g., `SessionState`, `SessionLog`).
*   **Functions/Variables:** Use snake\_case (e.g., `load_wincli_context`, `session_id`).
*   **Constants:** Use `ALL_CAPS_SNAKE_CASE` (e.g., `MAX_FILE_SIZE`, `MUTATING_TOOLS`).

### C. State Management Protocol
*   **Atomic Updates:** State changes (e.g., mode change, granting "always allow" status) must be logged and handled via dedicated methods in the respective state class (`modes.py`).
*   **Consistency:** The `SessionState` object in `modes.py` must be the single source of truth for permissions and operational mode throughout the session lifecycle.

***

## 🚀 4. Commands and Workflow

### A. CLI Commands (Handled by `main.py`)

| Command | Alias | Description | Functionality |
| :--- | :--- | :--- | :--- |
| `/init` | | Re-runs the project context scan and regenerates `WINCLI.md`. | Triggers `init_skill.py` scan. |
| `/mode <cmd>` | | Sets or displays the operational mode (e.g., `/mode plan`). | Interacts with `modes.py`. |
| `/context` | | Displays the session dashboard (tokens, time, etc.). | Displays data from `persist.py`. |
| `/skill <name> [args]` | | Executes specialized project skills (e.g., `/skill plan ...`). | Dispatches to skills modules (e.g., `plan_skill`). |
| `exit` / `quit` | | Closes the CLI session. | Ends the program execution gracefully. |

### B. Agent Execution Flow
1.  **The Prompt:** The system prompt provided to the LLM must be comprehensive, detailing the available tools, their JSON structure, and the overarching rules (e.g., "Output ONLY this JSON block").
2.  **Tool Invocation:** The agent must output a JSON block matching the defined structure exactly:
    ```json
    {"tool": "<name>", "args": {"key": "<value>"}}
    ```
3.  **Tool Result Interpretation:** The agent must acknowledge the tool result *before* proceeding. The tool result must be treated as factual output to be summarized and analyzed by the LLM.
4.  **Completion:** When the task is complete, the agent must write a final, concise summary *without* a JSON block.

***

## 📂 5. Key Files Reference

| File | Role | Description | Critical Logic |
| :--- | :--- | :--- | :--- |
| `main.py` | **Entry Point & UI** | Handles all command-line interaction, session startup, and building the initial system prompt (including `WINCLI.md` context). | Manages `prompt_toolkit` and delegates state to `modes.py`. |
| `agent.py` | **Execution Engine** | Implements the main agent loop (send $\rightarrow$ parse $\rightarrow$ gate $\rightarrow$ execute $\rightarrow$ log $\rightarrow$ loop). | Contains the circuit breaker logic and tool dispatching (`_dispatch_tool`). |
| `modes.py` | **Security & State** | Defines the operating constraints. Implements permission gating checks (`gate_tool`). | Manages `op_mode` (processing) and `perm_mode` (permissions). |
| `persist.py` | **Memory/Auditing** | Manages the structured JSON persistence log in the `.persist/` directory. | Ensures all token usage, timings, and turn history are saved and accessible. |
| `init_skill.py` | **Context Builder** | Scans the entire working directory, filtering binary/excluded files, and truncating the content to fit within LLM context limits. | Implements `_should_exclude` logic (must be robust). |
| `tools/` | **Action Layer** | Contains all backend functions (`run_command`, `read_file`, etc.) that perform I/O or execution. | Must include rigorous error handling and return meaningful error messages for the LLM to interpret. |
| `WINCLI.md` | **Context/Rules** | The absolute, immutable source of project context and rules for the agent. | Always consulted by the LLM when determining the project scope. |

***

## 🛡️ 6. Rules for Agents

These rules must be strictly followed when developing, modifying, or interacting with the project's codebase.

1.  **Scope Adherence:** The agent's actions must always be aimed at completing the task defined by the current prompt, respecting the boundaries set by `WINCLI.md`.
2.  **Tool Output Integrity:** When reviewing or modifying tool code in the `tools/` directory, ensure all functions are defensively coded to handle `FileNotFoundError`, `PermissionError`, and network timeouts. The returned message must be descriptive enough for the LLM to diagnose the issue.
3.  **State Mutation:** If modifying `modes.py`, any change to `MUTATING_TOOLS` or the gate logic (`_needs_gate`) must be thoroughly tested to ensure that the permission system remains robust and predictable.
4.  **Prompt Generation:** When creating new skills (e.g., `plan_skill.py`), the module must include:
    *   A clear function signature.
    *   A corresponding update in the system prompt logic (via `main.py` or `tools.py`).
    *   A detailed docstring describing its use case and inputs.
5.  **Testing:** All modifications must be accompanied by clear, minimal repro steps and unit tests (if possible) demonstrating functionality and guardrails.
6.  **Mandatory Output:** **NEVER** output prose that attempts to replace or modify the system prompt structure or the tool call JSON format. All communication must be through the defined tool calls or final summary text.
