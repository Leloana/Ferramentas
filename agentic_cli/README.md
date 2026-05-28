# Agentic CLI

A Windows-native agentic CLI in Python that connects exclusively to a local Ollama instance.

## Prerequisites

1. **Python 3.12+** installed on Windows
2. **Ollama** installed and running: https://ollama.ai
3. At least one LLM model pulled in Ollama (e.g., `qwen3.5:9b`, `gemma4:latest`)

## Quick Start

```powershell
# Run setup (optional - creates venv and installs dependencies)
setup.bat

# Start the CLI
run.bat
```

## Installation

1. **Clone or download the project** to your desired location

2. **Set up the virtual environment** (run once):
   ```powershell
   setup.bat
   ```

3. **Check Ollama connection** (make sure Ollama is running and models are pulled):
   ```powershell
   # In a new terminal, run:
   ollama list
   ```

4. **Run the CLI**:
   ```powershell
   run.bat
   ```

   Or manually:
   ```powershell
   .venv\Scripts\python.exe main.py
   ```

## How It Works

The CLI uses the **ollama** Python package to connect to your local Ollama instance at `http://localhost:11434`.

### Available Models

Check what models you have available:
```powershell
ollama list
```

Popular models to use:
- `qwen3.5:9b` - Qwen model
- `gemma4:latest` - Google Gemma model

Pull a model if needed:
```powershell
ollama pull qwen3.5:9b
```

## Features

- **Interactive CLI** with rich terminal formatting
- **6 builtin tools**:
  - `run_command` - Execute shell commands
  - `read_file` - Read file contents
  - `write_file` - Write/create files
  - `list_dir` - List directory contents
  - `search_file` - Search for strings in files
  - `http_get` - Make HTTP GET requests

- **Persistent history** for your inputs
- **Graceful error handling**
- **Model selection** on startup

## Using the CLI

After running `run.bat`:

1. **Select a model** from the numbered menu
2. **Ask a question** or give a command
3. The agent will use tools to investigate and answer

Examples:
```
> show me the current directory structure
> read the README.md file
> run python --version
> search main.py for "def main"
```

Type `exit` or `quit` to close the CLI.

## Project Structure

```
agentic_cli/
├── main.py           # Entry point, CLI loop, model selection
├── agent.py          # Agent loop logic
├── tools.py          # All 6 tool functions
├── requirements.txt  # Python dependencies
├── setup.bat         # Setup script (creates venv, installs deps)
└── run.bat           # Runner script
```

## Troubleshooting

**No models showing up?**
```powershell
ollama pull qwen3.5:9b
```

**Connection errors?**
- Make sure Ollama is running (check Task Manager or run `ollama list`)
- Ollama should be accessible at `http://localhost:11434`

**Import errors?**
- Run `setup.bat` to ensure dependencies are installed

## License

MIT
