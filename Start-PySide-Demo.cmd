@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -c "import PySide6.QtWidgets,pygame" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
exit /b 0
:fail
echo Setup failed. Install Windows Python 3.11 and retry.
pause
exit /b 1
