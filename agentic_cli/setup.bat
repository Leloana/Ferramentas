@echo off
echo Creating virtual environment...
if not exist .venv (
    python -m venv .venv
) else (
    echo Virtual environment already exists.
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing dependencies...
.venv\Scripts\pip install -r requirements.txt

echo Setup complete! Run run.bat to start the CLI.
pause
