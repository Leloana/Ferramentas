@echo off
set PYTHONPATH=%~dp0
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
) else (
    echo Virtual environment not found. Please run setup.bat inside the agentic_cli directory first.
)
