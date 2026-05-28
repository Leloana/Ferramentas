@echo off
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe main.py
) else (
    echo Virtual environment not found. Run setup.bat first.
)
