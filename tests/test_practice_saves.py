"""Practice save evidence is independent of a browser, the live port and real save files."""

import hashlib
import json
import socket
import sqlite3
from contextlib import closing
from time import monotonic, sleep

from fastapi.testclient import TestClient
from test_live_udp import packets

from practice_saves import PracticeSaves
from server import app


def practice(epoch=1, lap=2, times=(83000,), **kwargs):
    return {
        "uid": "18446744073709551611",
        "epoch": epoch,
        "sessionType": 1,
        "player": 0,
        "cars": [
            {
                "slot": 0,
                "lap": lap,
                "currentMs": 400,
                "history": [(ms, (), 15) for ms in times],
            }
        ],
        **kwargs,
    }


def test_snapshots_baseline_rewind_restart_and_late_write(tmp_path):
    source = tmp_path / "steam"
    source.mkdir()
    file = source / "savegame@profile#binary"
    other = source / "savegame@highlights000#binary"
    other.write_bytes(b"unrelated")
    file.write_bytes(b"before")
    watcher = PracticeSaves(tmp_path / "archive", source)
    watcher.tick({})
    file.write_bytes(b"menu-change")
    watcher.tick({})
    assert not watcher.path.exists()
    watcher.tick(practice(handoff=True))
    assert not watcher.path.exists()
    watcher.tick(practice())
    file.write_bytes(b"on-track")
    watcher.tick(practice(lap=3, times=(83000, 82000)))
    watcher.tick(practice(lap=3, times=(83000, 82000)))
    watcher.tick(practice(epoch=2, lap=2))
    watcher.tick(practice(sessionType=8))
    file.write_bytes(b"after-FP")
    mtime = file.stat().st_mtime_ns
    watcher.tick(practice(sessionType=8))
    reopened = PracticeSaves(tmp_path / "archive", source)
    (session,) = reopened.report()["sessions"]
    assert (
        session["completedLaps"],
        session["unclassifiedLaps"],
        session["programmeCounts"],
    ) == (1, 1, None)
    assert session["changedFilesObserved"] == 2
    with closing(sqlite3.connect(watcher.path)) as db:
        blobs = dict(db.execute("SELECT hash,data FROM blobs"))
        assert set(blobs.values()) == {
            b"before",
            b"menu-change",
            b"on-track",
            b"after-FP",
        }
        assert all(hashlib.sha256(v).hexdigest() == k for k, v in blobs.items())
        entries = [
            (kind, json.loads(ctx))
            for kind, ctx in db.execute(
                "SELECT kind,context FROM observations WHERE file IS NOT NULL ORDER BY id"
            )
        ]
        assert entries[0][0] == "before-fp" and "lap" not in entries[0][1]
        assert [ctx["lap"] for kind, ctx in entries if kind == "changed"] == [3]
        assert entries[-1][0] == "after-fp-changed"
    assert (file.read_bytes(), file.stat().st_mtime_ns) == (b"after-FP", mtime)
    assert other.read_bytes() == b"unrelated"


def test_live_udp_captures_without_dashboard(tmp_path, monkeypatch):
    source = tmp_path / "steam-remote"
    source.mkdir()
    file = source / "savegame@midsessions0#file"
    file.write_bytes(b"before-start")
    monkeypatch.setenv("F125_UDP_PORT", "0")

    def wait(check):
        deadline = monotonic() + 7
        while monotonic() < deadline:
            if check():
                return
            sleep(0.05)
        raise AssertionError("practice observer did not publish in time")

    with (
        TestClient(app) as client,
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender,
    ):

        def report():
            return client.get("/api/practice-saves").json()

        wait(lambda: report()["watcher"]["files"] == 1)
        fixture = packets(2026, uid=123456)
        fixture[1][35] = 1
        for packet in fixture.values():
            sender.sendto(packet, ("127.0.0.1", app.state.udp.port))
        wait(lambda: len(report()["sessions"]) == 1)
        file.write_bytes(b"programme-finished")
        wait(lambda: report()["sessions"][0]["changedFilesObserved"] == 1)
        assert report()["sessions"][0]["laps"] == {"6": {"ms": 90800, "valid": True}}
        assert report()["watcher"]["state"] == "Recording"
