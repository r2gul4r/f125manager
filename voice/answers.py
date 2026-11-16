"""Read fresh live data for a short English driver radio reply."""

import json
import os
import subprocess
from pathlib import Path

from websockets.sync.client import connect


def ask_engineer(port, text, folder):
    with connect(f"ws://127.0.0.1:{port}/ws/live", proxy=None, open_timeout=3) as ws:
        packet = json.loads(ws.recv(timeout=5))
        frame = packet.get("frame") or {}
        if packet.get("status") != "Live" or frame.get("player", -1) < 0:
            return {"speech": "Waiting for live telemetry."}, frame, None
        damage = wing(frame, folder)
        ws.send(
            json.dumps(
                {
                    "type": "radio",
                    "key": os.environ["F125_RADIO_TURN_KEY"],
                    "question": text,
                    "session": frame["session"],
                    "wingDamage": damage,
                }
            )
        )
        while True:
            packet = json.loads(ws.recv(timeout=95))
            if "radio" in packet:
                return packet["radio"], frame, damage


def wing(frame, recordings):
    rec = frame.get("recordingId", "")
    if not rec or Path(rec).name != rec:
        return None
    py = Path(
        os.environ.get(
            "F125_ZSTD_PYTHON",
            Path(os.environ["LOCALAPPDATA"]) / "Programs/Python/Python314/python.exe",
        )
    )
    try:
        data = json.loads(
            subprocess.check_output(
                [py, Path(__file__).with_name("read_damage.py"), recordings / rec],
                timeout=2,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    stamp = frame.get("displayStamp") or {}
    if (
        data
        and str(data[1]) == frame["session"].split("/")[0]
        and abs(stamp.get("at", -10000) - data[0]) < 3500
        and max(data[2:]) <= 100
    ):
        return data[2:]
