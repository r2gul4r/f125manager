"""One local radio worker per dashboard server. UDP capture never waits for audio."""

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from threading import Lock, Thread


class Microphone:
    def __init__(self, port, recordings):
        self.runtime = Path(
            os.getenv("F125_VOICE_DIR", Path(__file__).parent / "output/tts-q4-bench")
        )
        self.port, self.recordings = port, recordings
        self.process = None
        self.turn_key = None
        self.lock = Lock()
        self.status = "off"
        self.result = {}

    def state(self):
        with self.lock:
            return {
                "enabled": self.process is not None,
                "status": self.status,
                **self.result,
            }

    def enable(self):
        with self.lock:
            if self.process is not None:
                return
            if not (self.runtime / "vk3/voice-speaker.exe").is_file():
                raise ValueError("Local voice runtime is missing")
            turn_key = secrets.token_urlsafe(32)
            env = {
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "HF_HUB_OFFLINE": "1",
                "F125_RADIO_TURN_KEY": turn_key,
                "PYTHONPATH": str(self.runtime / "asr-libs"),
            }
            p = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    str(Path(__file__).parent / "voice/worker.py"),
                    str(self.runtime),
                    str(self.port),
                    str(self.recordings),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.process, self.status, self.result = p, "warming", {}
            self.turn_key = turn_key
        Thread(target=self._read, args=(p,), daemon=True).start()

    def _read(self, p):
        try:
            for line in p.stdout:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                with self.lock:
                    if self.process is p:
                        self.status = item.pop("status")
                        self.result.update(item)
        finally:
            with self.lock:
                if self.process is p:
                    self.process = None
                    self.turn_key = None
                    self.status = "error"

    def press(self):
        with self.lock:
            if self.process is None:
                return False
            if self.status == "ready":
                try:
                    self.process.stdin.write("listen\n")
                    self.process.stdin.flush()
                    self.status = "opening"
                except (ValueError, OSError):
                    self.status = "error"
            return True

    def disable(self):
        with self.lock:
            self.turn_key = None
            p, self.process, self.status = self.process, None, "off"
            self.result = {}
        if p:
            try:
                p.stdin.close()
                p.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                p.kill()
                p.wait()
