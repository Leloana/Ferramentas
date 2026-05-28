# Agentic CLI

A Windows-native agentic CLI in Python that drives a local Ollama model
through a tool-calling loop. Built around two pillars:

1. **Windows-native** — every shell command runs through `powershell.exe`,
   the `/plan` editor defaults to `notepad`, the bundled `setup.bat` /
   `run.bat` handle the venv.
2. **Minimal default context** — the LLM system prompt only describes the
   core tools (~350 tokens). Skills and slash commands are exposed *to
   you* in the terminal but never injected into the model's context until
   invoked.

## Prerequisites

1. **Python 3.12+** on Windows
2. **Ollama** running locally: <https://ollama.ai>
3. A model with decent tool-calling — `qwen3.5:9b` is the tested default

## Quick start

```powershell
setup.bat        # one-time: create venv, install deps
run.bat          # launch the CLI
```

Inside the CLI, pick a model from the menu and you're in.

## What's in the box

### Core tools (always available, in the LLM's prompt)

| tool | purpose |
|------|---------|
| `run_command`  | execute a PowerShell command (capped output) |
| `read_file`    | read with numbered lines, supports `offset`/`limit` |
| `write_file`   | create or overwrite a file |
| `patch_file`   | edit an existing file (3 variants — see below) |
| `list_dir`     | list directory contents |
| `search_file`  | grep a single file |
| `http_get`     | HTTP GET (truncated body) |

### Slash commands (terminal-side, never in LLM context)

| command | purpose |
|---------|---------|
| `/init`            | scan project and (re)generate `WINCLI.md` |
| `/mode [args]`     | show or change op/perm mode |
| `/context`         | session dashboard + diff stats |
| `/skills`          | list available skills |
| `/skill <name> …`  | invoke a skill by name |
| `/plan <prompt>`   | shortcut for `/skill plan …` (multi-agent) |
| `/debug <cmd> ‖‖‖ <criterion>` | shortcut for `/skill debug …` (multi-round) |
| `/reflect [hint]`  | shortcut for `/skill reflect …` |
| `/add_skill <desc>`| scaffold a new skill via the LLM |
| `/add_tool <desc>` | scaffold a new tool via the LLM |
| `/resume [id|last]`| reload a previous session from `.persist/` |
| `/undo [N]`        | revert the last N file edits |
| `exit` / `quit`    | leave |

### Skills (lazy-loaded from `skills/`)

| skill | what it does |
|-------|--------------|
| `init`     | wraps `init_skill.py` — regenerate `WINCLI.md` |
| `plan`     | multi-agent: planner → reviewer → user approval → executors → verifier |
| `debug`    | multi-round: 3 rounds with context refresh and handoffs |
| `reflect`  | step back, summarize stuck state, propose new approach |
| `add_skill`| LLM scaffolds a new skill file |
| `add_tool` | LLM scaffolds a new tool (appended to `extra_tools.py`) |

Skills are discovered by reading `NAME`/`DESCRIPTION` lines without
importing the module. Only the user sees the list; the LLM only learns
about a skill when you `/skill <name>` it.

## How prompts get processed

```
prompt_toolkit input
   ↓
slash-command dispatcher  (/mode, /context, /resume, /undo, /skill, …)
   ↓ (if not a slash command)
run_agent_loop  →  Ollama (streaming)
   ↓ tool call?
   ├─ permission gate (modes.py, depending on /mode setting)
   ├─ snapshot if mutating (snapshot.py)
   ├─ execute (tools.py CORE_TOOLS, then extra_tools.py)
   ├─ feed result back as next user message
   └─ loop
```

## Modes and permissions

Two orthogonal axes:

- **op_mode**:   `normal` | `plan` | `debug`   (currently flavor; per-skill flows do the heavy lifting)
- **perm_mode**: `bypass` | `ask_edits` (default) | `ask_all`

In `ask_edits`, every `write_file`/`patch_file`/`run_command` shows a
diff/preview panel and prompts:

- `y` allow once
- `n` deny
- `a` always allow this tool this session
- `p` always allow this tool for this specific path

Change with `/mode bypass` etc. State visible in `/context`.

## Three `patch_file` variants

Edit `ACTIVE_PATCH` at the top of [`tools.py`](tools.py):

- `v1` — `old_str` + `new_str`, must be a unique match. Errors include
  fuzzy hints of similar lines.
- `v2` — `old_str` + `new_str` + `context_before` + `context_after`
  anchors. Disambiguates when `old_str` appears in multiple places.
- `v3` — `start_line` + `end_line` + `new_content`. No string matching —
  pairs with `read_file`'s numbered output for surgical edits.

## Persistence (`.persist/`)

Every session writes a JSON log to `.persist/<session_id>.json`:

```json
{
  "session_id": "20260528_..._abc123",
  "started_at": "...",
  "model": "qwen3.5:9b",
  "resumed_from": null,
  "turns": [
    {
      "user": "...",
      "chain": [{"kind": "assistant", "content": "...",
                 "prompt_tokens": 0, "gen_tokens": 0, "elapsed_s": 0.0,
                 "tps": 0.0, "tool_call": null, "tool_result": null}],
      "totals": {...}
    }
  ],
  "session_totals": {...}
}
```

Snapshots of every edited file go to
`.persist/snapshots/<session_id>/<seq>/<filename>` so `/undo` can revert.

## Context hygiene

- `read_file` caps at 300 lines (head + omitted + tail). Use
  `offset`/`limit` for specific ranges.
- `run_command` caps `stdout`/`stderr` at 100 lines each.
- Tool results older than 5 user-turns are replaced by one-line
  summaries before sending to Ollama — disk persistence keeps the full
  content for `/resume` and debugging.

## Multi-agent plan flow

`/plan <prompt>` runs:

```
1. PLANNER       → markdown with (id:N, deps:X,Y, tools:a,b) tasks
2. REVIEWER      → critiques + rewrites vague tasks
3. USER APPROVAL → a/e/r/c  (e opens notepad for direct edit)
4. EXECUTORS     → one fresh subagent per task, in topo order,
                   respects deps (failed dep → cascading skip)
5. VERIFIER      → read-only, adversarial; produces JSON verdict
6. REPORT        → table + injection into main conversation
```

All subagents run **serially**, **same model**, `keep_alive=10m` so the
GPU keeps the model loaded between calls. Designed for ≤12GB VRAM.

## Multi-round debug flow

`/debug <command> ||| <criterion>` runs up to 3 rounds, each with a
fresh subagent context. If a round can't solve it, it emits a
` ```handoff ` block (TRIED / LAST_ERROR / FILES_TOUCHED / HYPOTHESIS /
NEXT) that's passed to the next round — gives the next attempt
condensed knowledge without the inflated history.

## Customization

- **Add a skill**: `/skill add_skill <description>` (LLM writes the
  file, index reloads on the fly), or drop a Python file in `skills/`
  exporting `NAME`, `DESCRIPTION`, `run(args, ctx)`.
- **Add a tool**: `/skill add_tool <description>` (appended to
  `extra_tools.py`, hot-reloaded by the dispatcher on the next call).
- **Tweak prompts**: subagent prompts live in `skills/plan.py` and
  `skills/debug.py`. The main agent's prompt is built in
  `main.build_system_prompt`.

## Project layout

```
agentic_cli/
├── main.py             # entry, slash dispatch, REPL
├── agent.py            # main agent loop (stream, parse, gate, snapshot,
│                       #   execute, persist, circuit-breaker, Ctrl+C)
├── subagent.py         # isolated sub-agent used by multi-agent flows
├── tools.py            # CORE_TOOLS + 3 patch variants
├── modes.py            # op/perm state + permission gate + previews
├── persist.py          # .persist/ JSON session logs + resume
├── snapshot.py         # per-edit snapshots + undo stack + diff stats
├── init_skill.py       # legacy: WINCLI.md generator (wrapped by skills/init.py)
├── plan_skill.py       # legacy single-agent /plan (kept for reference)
├── skills/
│   ├── __init__.py     # lazy-load skill registry
│   ├── init.py
│   ├── plan.py         # multi-agent plan
│   ├── debug.py        # multi-round debug
│   ├── reflect.py
│   ├── add_skill.py
│   └── add_tool.py
├── extra_tools.py      # created by /skill add_tool (optional)
├── plans/              # generated by /plan
├── .persist/           # session JSON + snapshots
├── WINCLI.md           # project context loaded into system prompt
├── setup.bat
└── run.bat
```

## Troubleshooting

- **`powershell.exe not found`** → you're not on Windows (this CLI is
  Windows-targeted).
- **Ollama not reachable** → `ollama list` to verify; the daemon should
  be on `http://localhost:11434`.
- **No models** → `ollama pull qwen3.5:9b`.
- **Window getting full (e.g. 28k/32k)** → check `/context` for big tool
  results; old ones get auto-summarized but the truncation thresholds
  in `tools.py` (`READ_FILE_MAX_LINES`, `RUN_COMMAND_MAX_LINES`) can be
  lowered.

## License

MIT
