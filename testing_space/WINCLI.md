# WINCLI.md — Project Context for AI Agents

## Project Overview
This project uses **WinCLI** (Windows CLI agent) for AI-assisted development.
WinCLI is an Ollama-powered agentic CLI that can read, write, patch, and run
commands in this project. It is configured via WINCLI.md.

## Tech Stack
<!-- TODO: describe languages, frameworks, and tools used in this project -->

## Architecture
<!-- TODO: describe how the code is organized, main components, and data flow -->

## Conventions
- Follow existing code style and naming patterns in the project.
- Use the tools provided by WinCLI: `read_file`, `write_file`, `patch_file`,
  `run_command`, `list_dir`, `search_file`, `http_get`.
- When modifying existing files, prefer `patch_file` over `write_file`.
- When creating new files, use `write_file`.
- Commands are PowerShell (`Get-ChildItem`, not `ls`).

## Commands
<!-- TODO: how to run, build, and test this project -->

## Key Files
<!-- TODO: list and describe the most important files in the project -->

## Rules for Agents
- One tool call per turn.
- After calling a tool, wait for the result before the next call.
- When you have the final answer, output it directly without a JSON tool block.
- If WINCLI.md exists, follow its conventions and rules.
- Final answers should be short summaries unless asked for detail.
