@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
  if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -c "import webview,openai_codex,fastapi,uvicorn,dotenv,websockets,pygame,cv2,numpy,PIL; from f125_core import UdpReceiver, Replay; from importlib.metadata import version; assert version('f125-core') == '0.2.40'" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements-web.txt
  if errorlevel 1 goto fail
)
if not exist "web\dist\index.html" (
  pushd web
  call npm.cmd ci --no-audit --no-fund
  if errorlevel 1 goto fail
  call npm.cmd run build
  if errorlevel 1 goto fail
  popd
)
".venv\Scripts\python.exe" start_web.py
if errorlevel 1 goto fail
exit /b 0
:fail
echo Dashboard startup failed. Check the error above, then retry.
pause
exit /b 1
