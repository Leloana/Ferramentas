)
   - Parse tool calls from JSON
   - Gate via modes.gate_tool()
   - Execute tool (tools.CORE_TOOLS or extra_tools)
   - Log step to persist.SessionLog
   - Display Rich Panel output
4. Session persistence: JSON dump to .persist/*.json
```

### Core Loop Components (agent.py)
- `strip_think_blocks()`: Remove `</think>` blocks from assistant responses
- `parse_tool_call()`: Extract JSON tool calls from responses
- `_dispatch_tool()`: Resolve tool from CORE_TOOLS or extra_tools.py
- `execute_tool()`: Execute with circuit breaker (3 consecutive failures trigger reflect)
- `_error_hint()`: Provide recovery suggestions based on error type

---

## Conventions

### Code Style
- **Python**: Use 4-space indents, no trailing whitespace, black-compatible style
- **PowerShell**: Commands use `Get-ChildItem`, `Read-Host`, etc.
- **JSON**: Compact for tool calls, pretty-printed for logs

### Naming Patterns
| Type | Pattern | Examples |
|------|---------|----------|
| Functions | `snake_case` | `strip_think_blocks`, `load_wincli_context` |
| Classes | `PascalCase` | `SessionLog`, `SessionState` |
| Modules | `module_name` | `agent`, `main`, `modes` |
| Variables | `snake_case` | `wincli_content`, `session_id` |
| Commands | `/command [args]` | `/init`, `/mode edit`, `/skill plan` |

### File Organization
- **Core logic**: `agent.py`, `main.py`, `modes.py`, `persist.py`
- **Skills**: `init_skill.py`, `plan_skill.py`, `debug_skill.py`
- **Tools**: `tools.py` (CORE_TOOLS dict), `extra_tools.py` (dynamic additions)
- **Persistence**: All `.json` files in `.persist/` directory
- **Context**: `WINCLI.md` at root for project-specific rules

### Permission Modes
| Mode | Description | Default |
|------|-------------|---------|
| `normal` | Standard agent operation | — |
| `plan` | Generate structured plans | — |
| `debug` | Lower-level debugging | — |

| Permission | Description | Default |
|-----------|-------------|---------|
| `bypass` | All tools allowed | — |
| `ask_edits` | Only gating mutating tools (`write_file`, `patch_file`, `run_command`) | — |
| `ask_all` | Require confirmation for all mutating tools | — |

---

## Commands

### Available Slash Commands
```
/init                    # Regenerate WINCLI.md with project context
/mode [normal|plan|debug] # Set operation mode
/mode [bypass|ask_edits|ask_all] # Set permission mode
/mode focus              # Enter focus mode (minimal UI)
/context                 # Show session dashboard (tokens, turns, model)
/skill <name> [args]     # Invoke a skill from skills/
/skills                  # List available skills
/plan <prompt>           # Shortcut for /skill plan <prompt>
/debug <cmd> ||| <ok>    # Shortcut for /skill debug
/reflect [hint]          # Shortcut for /skill reflect
/exit / quit             # Exit the CLI
```

### Example Usage
```bash
# Start a new session
> /init

# Set read/write permissions (asks only for edits)
> /mode ask_edits

# Enter plan mode for structured planning
> /mode plan

# View current session state
> /context

# Generate a plan file
> /plan implement authentication system

# List available skills
> /skills
```

---

## Key Files

### agent.py
**Purpose**: Core agent loop implementation
**Functions**:
- `run_agent_loop()`: Main execution loop
- `parse_tool_call()`: Extract JSON tool calls
- `execute_tool()`: Execute with error handling
- `_error_hint()`: Generate recovery suggestions

### main.py
**Purpose**: CLI entry point and command routing
**Key Features**:
- Builds system prompt with WINCLI.md content
- Handles Ctrl+C gracefully (no signal handler)
- Renders Rich console with token counters
- Manages session state via `SessionState`

### init_skill.py
**Purpose**: Generate WINCLI.md and scan projects
**Key Functions**:
- `_scan_project_with_feedback()`: Live progress display during scanning
- `_is_text_file()`: Check if file is readable text
- `generate_wincli()`: Create WINCLI.md from project analysis

### persist.py
**Purpose**: Session logging to JSON
**Class**: `SessionLog`
- Tracks tokens, timing, tool calls
- Supports session resumption
- Files stored in `.persist/<id>.json`

### modes.py
**Purpose**: Mode/permission state management
**Class**: `SessionState`
**Functions**:
- `gate_tool()`: Permission gating
- `_diff_preview()`: Render tool diff previews
- `handle_mode_command()`: Process /mode commands

### tools.py (implied)
**Purpose**: Tool definitions and execution
**Variables**:
- `CORE_TOOLS`: Dict of registered tools
- `ACTIVE_PATCH`: Current patch_file variant (v1/v2/v3)
- `MUTATING_TOOLS`: Set of state-modifying tools

### plan_skill.py (mentioned in fazer.txt)
**Purpose**: Generate structured plans as markdown files
**Behavior**:
1. Use LLM to generate plan from prompt
2. Save to `plans/<slug>.md`
3. Display in Rich Panel
4. Append to conversation history

---

## Rules for Agents

### When Modifying Files

1. **WINCLI.md is Source of Truth**: Any project context should update WINCLI.md first. Do not hard-code assumptions that contradict WINCLI.md.

2. **Use patch_file for Modifications**: Never use write_file on existing files. Use patch_file with:
   - v1: `{path, old_str, new_str}` (first unique match)
   - v2: `{path, old_str, new_str, context_before, context_after}`
   - v3: `{path, start_line, end_line, new_content}` (line numbers)

3. **Always Check for indent issues**: patch_file failures often caused by indentation. Use read_file to inspect before patching.

4. **Strip Thinking Blocks**: Before parsing tool calls, remove `</think>` blocks from assistant responses using `strip_think_blocks()`.

5. **Respect Permission Gating**: Call `modes.gate_tool()` before executing mutating tools. Handle user confirmations gracefully.

6. **Log Every Step**: Use `SessionLog.log_step()` for each tool execution. Never skip logging.

7. **Handle Circuit Breaker**: If a tool fails 3 times consecutively (same args_hash), auto-trigger `reflect` skill for analysis.

### When Generating Plans

1. **Use /plan Command**: For plan generation, always use `/plan <prompt>` which writes to `plans/` folder.

2. **Slugify Filenames**: Convert prompts to lowercase-with-dashes (e.g., `implement-authentication-system.md`).

3. **Display Plans**: Always show generated plans in Rich Panel before completing the task.

4. **Track in History**: Append plans to conversation history so future messages reference them.

### Tool Execution Rules

1. **One Tool Per Turn**: Never call multiple tools in a single response.

2. **Wait for Results**: After a tool call, wait for the result before calling the next tool.

3. **Handle Errors Gracefully**: Use `_error_hint()` to provide recovery suggestions.

4. **PowerShell Commands**: Use `run_command` with valid PowerShell syntax (Get-ChildItem, not ls).

### Session Management

1. **Session ID**: Automatically generated timestamp+UUID (e.g., `20260528_161554_b73eb8`).

2. **Model Info**: Track which model is being used (currently `qwen3.5:9b`).

3. **Token Tracking**: Monitor `prompt_tokens` and `gen_tokens` for cost awareness.

4. **Elapsed Time**: Track total session duration in `.persist/*.json`.

### Best Practices

1. **Start with /init**: Always regenerate WINCLI.md when starting fresh to ensure up-to-date context.

2. **Use /mode**: Set operation and permission modes early in the session.

3. **Check WINCLI.md**: Before any major change, verify WINCLI.md contains the relevant rules.

4. **Small Payloads**: For large operations, break into smaller steps to avoid timeouts.

5. **Respect Max File Size**: Don't try to read files >100KB in a single operation.

6. **Binary Files**: Use `_is_text_file()` before attempting to read files.

---

## Session Persistence Format

Each `.persist/<id>.json` follows this schema:

```json
{
  "session_id": "20260528_161554_b73eb8",
  "started_at": "2026-05-28T19:15:54.837793+00:00",
  "model": "qwen3.5:9b",
  "resumed_from": null,
  "turns": [
    {
      "user": "<input>",
      "chain": [
        {
          "kind": "assistant" | "tool",
          "content": "assistant text or tool result",
          "prompt_tokens": 123,
          "gen_tokens": 456,
          "elapsed_s": 12.3,
          "tps": 35.0,
          "tool_call": null | {"name": "read_file", "args": {...}},
          "tool_result": null | { ... }
        }
      ],
      "totals": {
        "prompt_tokens": 234,
        "gen_tokens": 789,
        "elapsed_s": 25.0
      }
    }
  ],
  "session_totals": {
    "prompt_tokens": 234,
    "gen_tokens": 789,
    "elapsed_s": 25.0
  }
}
```

---

## Error Recovery Patterns

1. **File Not Found**: Suggest using `list_dir` to verify path spelling.
2. **Permission Denied**: Check file ownership or use different approach.
3. **JSON Parse Errors**: Re-read the source and retry with exact strings.
4. **Timeouts**: Break operation into smaller payloads.
5. **Network Issues**: Retry or check the URL/host.

When errors occur 3+ times:
1. Extract error from `_error_hint()` suggestions
2. Auto-trigger `reflect` skill for analysis
3. Summarize to user and offer alternatives

---

## Extending the Project

### Adding a New Tool

1. Create `extra_tools.py`
2. Export function with same name as tool (e.g., `my_new_tool`)
3. Ensure it returns appropriate result structure
4. Agent automatically discovers via `_dispatch_tool()`

### Adding a New Skill

1. Create `skills/<name>.py` or use `/skill <name>` in main.py
2. Export function with clear docstring
3. Wire up in `main.py` slash command routing

### Adding a New Permission Mode

1. Extend `MUTATING_TOOLS` set in modes.py
2. Update `_needs_gate()` logic
3. Add documentation to WINCLI.md

---

## Quick Reference

| Task | Command | Notes |
|------|---------|-------|
| Start session | `/init` | Regenerates WINCLI.md |
| Set permissions | `/mode ask_edits` | Asks only for edits |
| Enter plan mode | `/mode plan` | Generates plans |
| View context | `/context` | Tokens, turns, model |
| Run PowerShell | `run_command` | Get-ChildItem, etc. |
| Read file | `read_file` | Returns numbered lines |
| Write new file | `write_file` | Create new |
| Modify file | `patch_file` | Use line numbers |
| List directory | `list_dir` | PowerShell Get-ChildItem |
| Search file | `search_file` | Pattern matching |
| Fetch URL | `http_get` | URL content fetch |

---

*Generated for: wincli project*
*WINCLI.md serves as the base project context, similar to CLAUDE.md for Claude Code.*
