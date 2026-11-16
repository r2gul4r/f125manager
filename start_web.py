"""Serve the built dashboard on loopback and open it once the listener is ready."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn
from dotenv import load_dotenv


def open_dashboard(url: str) -> None:
    subprocess.Popen([sys.executable, str(Path(__file__).with_name("desktop_window.py")), url])


def already_running(url: str) -> bool:
    try:
        with urlopen(url + "/api/health", timeout=0.5) as response:
            existing = json.load(response)
    except (URLError, OSError, ValueError):
        return False
    return isinstance(existing, dict) and existing.get("native_core") == "f125_core"


async def main() -> None:
    load_dotenv()
    port = int(os.getenv("F125_HTTP_PORT", "8765"))
    if not 1 <= port <= 65535:
        raise ValueError("F125_HTTP_PORT must be in 1..65535")
    url = f"http://127.0.0.1:{port}"
    if await asyncio.to_thread(already_running, url):
        open_dashboard(url)
        return
    server = uvicorn.Server(uvicorn.Config("server:app", host="127.0.0.1", port=port))
    task = asyncio.create_task(server.serve())
    while not server.started and not task.done():
        await asyncio.sleep(0.05)
    try:
        if server.started:
            open_dashboard(url)
    except (OSError, RuntimeError):
        server.should_exit = True
        await task
        raise
    await task


if __name__ == "__main__":
    asyncio.run(main())
