Build a Windows-native agentic CLI in Python that connects exclusively to a local Ollama instance. Follow every requirement below exactly.

1. VIRTUAL ENVIRONMENT

Create a venv at the project root using python -m venv .venv
All dependencies must be installed inside .venv
Create a setup.bat script that:

Runs python -m venv .venv
Runs .venv\Scripts\activate
Runs pip install -r requirements.txt


The main entry point must be run via .venv\Scripts\python.exe main.py
Create a run.bat that activates the venv and runs main.py


2. PYTHON LIBRARIES
Use exactly these libraries in requirements.txt:
ollama==0.4.4
rich==13.7.1
prompt_toolkit==3.0.47
pathlib2==2.3.7
requests==2.32.3

ollama — official Python client for Ollama API (no OpenAI, no LangChain)
rich — terminal output formatting, panels, markdown rendering, spinners
prompt_toolkit — interactive CLI input with history and autocompletion
requests — used internally by some tools for HTTP calls
pathlib2 — cross-platform path handling for file tools


3. AGENTIC TOOLS
Implement an agent loop that:

Sends user message + tool definitions to Ollama
Parses the model response for tool calls (JSON inside the response)
Executes the requested tool
Feeds the result back to the model as a follow-up message
Repeats until the model returns a final answer with no tool call

Implement these tools. Each tool is a Python function. The model selects tools by returning a JSON block in its response in this format:
json{"tool": "tool_name", "args": {"param": "value"}}
Tool 1: run_command

Purpose: Execute a Windows shell command and return stdout + stderr
Command internally: subprocess.run(args["command"], shell=True, capture_output=True, text=True, timeout=30)
Returns: {"stdout": "...", "stderr": "...", "returncode": 0}
Example model call: {"tool": "run_command", "args": {"command": "dir C:\\Users"}}

Tool 2: read_file

Purpose: Read the full contents of a file
Command internally: Path(args["path"]).read_text(encoding="utf-8")
Returns: {"content": "...file contents..."}
Example model call: {"tool": "read_file", "args": {"path": "C:\\project\\main.py"}}

Tool 3: write_file

Purpose: Write or overwrite a file with given content
Command internally: Path(args["path"]).write_text(args["content"], encoding="utf-8")
Returns: {"status": "ok", "path": "..."}
Example model call: {"tool": "write_file", "args": {"path": "C:\\project\\out.txt", "content": "hello"}}

Tool 4: list_dir

Purpose: List files and folders in a directory
Command internally: os.listdir(args["path"])
Returns: {"entries": ["file1.py", "subdir", ...]}
Example model call: {"tool": "list_dir", "args": {"path": "C:\\project"}}

Tool 5: search_file

Purpose: Search for a string inside a file, return matching lines with line numbers
Command internally: iterate Path(args["path"]).read_text().splitlines(), filter by args["query"]
Returns: {"matches": [{"line": 42, "content": "..."}]}
Example model call: {"tool": "search_file", "args": {"path": "C:\\project\\main.py", "query": "def run"}}

Tool 6: http_get

Purpose: Perform an HTTP GET request and return the response body (truncated to 3000 chars)
Command internally: requests.get(args["url"], timeout=10).text[:3000]
Returns: {"body": "..."}
Example model call: {"tool": "http_get", "args": {"url": "http://localhost:11434/api/tags"}}


4. OLLAMA CONNECTION

Connect only to Ollama at http://localhost:11434
Use the ollama Python package: import ollama
At startup, call ollama.list() to verify the connection; if it fails, print an error and exit
Let the user choose which local model to use from the listed models (shown as a numbered menu using rich)
All chat calls must use ollama.chat(model=selected_model, messages=conversation_history)
Maintain full conversation_history across turns so the model has context
The system prompt must instruct the model to call tools by outputting a JSON block wrapped in triple backticks like:
```json {"tool": "...", "args": {...}} ```
and to keep calling tools until it has enough information to give a final answer


PROJECT STRUCTURE
project/
├── main.py           # entry point, CLI loop, model selection
├── agent.py          # agent loop: send → parse → execute → loop
├── tools.py          # all 6 tool functions
├── requirements.txt
├── setup.bat
└── run.bat

BEHAVIOR REQUIREMENTS

Use rich.console.Console for all output (panels, colored text, spinners during model calls)
Use prompt_toolkit.prompt() for user input with persistent history saved to .history
Print each tool call and its result in a distinct colored panel before feeding it back to the model
On startup show: Ollama connection status, available models, selected model
Handle tool errors gracefully: catch exceptions, return {"error": "..."} and continue the loop
Exit cleanly on Ctrl+C or when user types exit or quit