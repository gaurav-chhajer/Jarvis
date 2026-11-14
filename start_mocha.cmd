@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Complete the Python environment setup in README.md first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "meeting_minutes_app.py"
