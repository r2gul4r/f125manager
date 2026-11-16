"""Real loopback datagrams, independent lifespans and a fresh native replay reader."""

import json
import socket
import struct
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient
from test_live_udp import packets

import f125_core
import recordings
from live_timing import live_frame
from server import app


@pytest.mark.parametrize("boundary", [None, "flashback", "stop"])
def test_seek_past_long_gap_keeps_only_same_stint_and_epoch(monkeypatch, boundary):
    class Reader:
        pit_loss_ms = 20000
        cursor = 0

        def advance(self, ms):
            self.cursor = ms
            epoch = int(boundary == "flashback" and ms >= 160000)
            return {"uid": "r", "epoch": epoch, "player": 0, "at": ms, "cars": [{"slot": 0, "result": 2}]}

    def frame_at(raw, **kwargs):
        after_stop = boundary == "stop" and raw["at"] >= 160000
        return {"session": raw["epoch"], "isRace": True, "mode": "race", "trackId": 1,
                "player": 0, "cars": [{"tyre": "M", "pit": False}], "lap": 4, "totalLaps": 15,
                "pitComparisons": [{"exitMs": 160000}] if after_stop else [],
                "forecast": {"plans": [{"id": "A"}]} if raw["at"] < 5000 else None}

    monkeypatch.setattr(recordings, "live_frame", frame_at)
    reader = Reader()
    raw = reader.advance(300000)
    view = recordings.restore_plan_preview(reader, 300000, ("r", raw["epoch"]))
    assert reader.cursor == 300000
    frame = frame_at(raw)
    view.update(frame, raw)
    assert bool(frame.get("previousPlans")) == (boundary is None)
    assert frame["forecast"] is None


def wait_for(read, check):
    deadline = monotonic() + 4
    while monotonic() < deadline:
        result = read()
        if check(result):
            return result
        sleep(0.01)
    pytest.fail("Timed out waiting for recording")


def drive_stop(year, address, sender, uid, frame, lane, position, include_field=False):
    wire = packets(year, uid, frame)
    me = 29 + 57
    wire[2][me + 46] = int(lane)
    wire[2][me + 34] = 2 if lane else 0
    wire[2][me + 32] = position
    wire[2][29 + 32] = 3 - position
    for key in [1, 4, 7, 6, 11, 0, 2] if include_field else [2]:
        sender.sendto(wire[key], address)


@pytest.mark.parametrize("year", [2025, 2026])
def test_record_and_reopen(year, monkeypatch):
    monkeypatch.setenv("F125_UDP_PORT", "0")
    with TestClient(app), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        rx = app.state.udp
        address = ("127.0.0.1", rx.port)
        drive_stop(year, address, sender, 888, 10, False, 2, True)
        live = wait_for(rx.snapshot, lambda s: s["boxNowPosition"] == 2 and s.get("recordingId"))
        assert live["timingFrame"] == 10 and live["timingMs"] >= 0
        sleep(0.04)  # Physically separate entry and exit in millisecond replay time.
        drive_stop(year, address, sender, 888, 11, True, 2)
        wait_for(rx.snapshot, lambda s: len(s["pitComparisons"]) == 1)
        sleep(0.04)
        drive_stop(year, address, sender, 888, 12, False, 1)
        stop = wait_for(rx.snapshot, lambda s: s["pitComparisons"][0][2] == 1)[
            "pitComparisons"
        ][0]
        assert stop[:3] == (7, 2, 1)
        drive_stop(year, address, sender, 999, 1, True, 2, True)
        wait_for(rx.snapshot, lambda s: s["uid"] == "999")
    # Changing today's settings must not rewrite yesterday's prediction.
    monkeypatch.setenv("F125_PIT_LOSS_MS", "5000")
    with TestClient(app) as client:
        sessions = client.get("/api/recordings").json()
        assert len(sessions) == 2
        cold, race = sessions
        assert (
            cold["stops"][0]["predicted"] is None and cold["stops"][0]["actual"] is None
        )
        row = race["stops"][0]
        assert race["id"] == live["recordingId"]
        review = client.get("/api/recordings/"+race["id"]+"/pit-review").json()[0]
        assert review["actual"]["position"] == 1 and review["forecasts"] == [None]*4
        assert (race["format"], race["pitLossMs"], row["predicted"], row["actual"]) == (
            year,
            20000,
            2,
            1,
        )
        with client.websocket_connect("/ws/replay/" + race["id"]) as ws:

            def seek(ms):
                ws.send_json({"type": "playback", "speed": 0, "ms": ms})
                return wait_for(
                    ws.receive_json,
                    lambda d: d["playback"]["ms"] == ms and d["playback"]["speed"] == 0,
                )["frame"]

            final = seek(race["durationMs"])
            assert final["source"] == "Replay" and final["pitComparisons"][0] == {
                k: v for k, v in row.items() if k != "epoch"
            }
            entry = seek(row["entryMs"])["pitComparisons"][0]
            assert entry["actual"] is None and entry["recalculated"] == 2
            assert seek(row["entryMs"] - 1)["pitComparisons"] == []
            assert seek(race["durationMs"])["pitComparisons"] == final["pitComparisons"]
        assert app.state.udp.snapshot()["accepted"] == 0
        root = app.state.record_dir / race["id"]
        # Change both historical labels. The packet-only entry result must
        # already exist before the exit and remain independent of both labels.
        manifest_file = root / "manifest.json"
        manifest = json.loads(manifest_file.read_bytes())
        manifest["stops"][0].update(predicted=3, actual=3)
        manifest_file.write_text(json.dumps(manifest))
        reader = f125_core.Replay(root)
        before = live_frame(reader.advance(row["entryMs"]))["pitComparisons"][0]
        after = live_frame(reader.advance(row["exitMs"]))["pitComparisons"][0]
        assert (before["predicted"], before["recalculated"], before["actual"]) == (3, 2, None)
        assert (after["predicted"], after["recalculated"], after["actual"]) == (3, 2, 1)
        chunk = next(root.glob("*.zst"))
        chunk.write_bytes(chunk.read_bytes()[:-4])
        with pytest.raises(OSError):
            f125_core.Replay(root).advance(race["durationMs"])


def calibration_packets(uid, frame, track, *, lane=False, gap=2000, service=0, safety=0, wing=0, age=6, weather=0):
    wire = packets(2026, uid, frame)
    damage = bytearray(1133)
    damage[:29] = wire[1][:29]
    damage[6] = 10
    damage[29+46+29] = wing
    wire[10] = damage
    wire[7][29+59+27] = age
    wire[1][29] = weather
    wire[1][36] = track
    wire[1][153] = safety
    wire[4][29] = 3
    rows = wire[2]
    me, rival = 29 + 57, 29 + 114
    rows[rival:rival+57] = rows[me:me+57]
    rows[rival+32] = 3 if gap <= 22000 else 2
    rows[me+32] = 5 - rows[rival+32]
    rows[me+34] = 2 if lane else 0
    rows[me+46] = int(lane)
    struct.pack_into("<H", rows, me+49, service)
    struct.pack_into("<H", rows, me+17, gap)
    struct.pack_into("<H", rows, rival+17, 22000)
    wire[7][29+118+26:29+118+28] = bytes((17, 6))
    return wire


def test_track_loss_feedback_and_replay(monkeypatch):
    monkeypatch.setenv("F125_UDP_PORT", "0")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        def send(uid, frame, track, **kwargs):
            batch = calibration_packets(uid, frame, track, **kwargs)
            address = ("127.0.0.1", app.state.udp.port)
            for key in [1, 4, 7, 11, 10, 2]:
                sock.sendto(batch[key], address)
            # Wait for the lap packet, not just the session packet.
            return wait_for(app.state.udp.snapshot, lambda s: s.get("cars") and s["uid"] == str(uid)
                            and s["cars"][1]["pit"] == kwargs.get("lane", False)
                            and s["cars"][1]["gapMs"] == kwargs.get("gap", 2000) and s["weather"] == kwargs.get("weather", 0))

        with TestClient(app):
            before = send(321, 1, 3)
            assert (before["boxNowPosition"], before["pitLossSamples"]) == (2, 0)
            unavailable = send(321, 2, 3, gap=0)
            assert unavailable["boxNowPosition"] is None
            send(321, 3, 3, lane=True, service=2300)
            sleep(.03)
            after = send(321, 4, 3, gap=26000, age=0)
            assert after["pitComparisons"][0][:3] == (7, 2, 3)
            assert (after["pitLossMs"], after["pitLossSamples"]) == (24000, 1)
            # Replay seeks in whole milliseconds; keep the next stop out of this exit timestamp.
            sleep(.01)
            later = send(321, 5, 3)
            assert later["boxNowPosition"] == 3
            assert live_frame(later)["forecast"]["rejoins"][0]["lossMs"] == 24000
            send(321, 6, 3, lane=True, service=2450)
            send(321, 7, 3, gap=30000, age=0)
            assert app.state.udp.snapshot()["pitLossMs"] == 26000
            send(321, 8, 3)
            send(321, 9, 3, lane=True, service=2450, safety=1)
            ignored = send(321, 10, 3, gap=10000)
            assert ignored["pitLossSamples"] == 2
            send(321, 11, 3, wing=66)
            send(321, 12, 3, lane=True, wing=66)
            repaired = send(321, 13, 3, gap=26000, service=2800)
            stop = live_frame(repaired)["pitComparisons"][-1]
            assert stop["serviceMs"] == 2800 and stop["wingRepair"] and stop["actual"] == 3
            assert repaired["pitLossSamples"] == 2
            send(321, 14, 3)
            send(321, 15, 3, lane=True, service=8000)
            slow = send(321, 16, 3, gap=26000)
            assert slow["pitLossSamples"] == 2
            wet = send(321, 17, 3, weather=4)
            assert wet["pitLossSamples"] == 0 and wet["pitLossMs"] == before["gamePitPriorMs"] + 5000
            isolated = send(322, 1, 7)
            assert (isolated["pitLossMs"], isolated["pitLossSamples"]) == (isolated["gamePitPriorMs"], 0)
            assert isolated["pitLossMs"] != before["pitLossMs"]

        with TestClient(app) as client:
            loaded = send(323, 1, 3)
            assert (loaded["boxNowPosition"], loaded["pitLossMs"], loaded["pitLossSamples"]) == (3, 26000, 2)
            race = next(r for r in client.get("/api/recordings").json() if r["uid"] == "321")
            reader = f125_core.Replay(app.state.record_dir / race["id"])
            entry, exit_ms = race["stops"][0]["entryMs"], race["stops"][0]["exitMs"]
            assert reader.advance(entry)["pitLossMs"] == before["gamePitPriorMs"]
            assert reader.advance(exit_ms)["pitLossMs"] == 24000
            assert reader.advance(entry)["pitLossSamples"] == 0

        # A v1 recording has only raw packets and frozen ranks. Its historical
        # forecast stays fixed, but the raw visit can inform the next race.
        path = app.state.record_dir / race["id"] / "manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["version"] = 1
        manifest.pop("observationSeeds")
        for stop in manifest["stops"]:
            stop.pop("lossMs", None)
        path.write_text(json.dumps(manifest), encoding="utf-8")
        assert f125_core.Replay(path.parent).advance(exit_ms)["pitLossMs"] == 20000
        with TestClient(app):
            restored = send(324, 1, 3)
            assert (restored["pitLossMs"], restored["pitLossSamples"]) == (26000, 2)

@pytest.mark.parametrize("safety", [1,2])
def test_rival_neutral_stop_is_measured_and_reloaded(safety,monkeypatch):
    monkeypatch.setenv("F125_UDP_PORT","0")
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
        def send(uid,frame,inside,loss,state):
            packets=calibration_packets(uid,frame,3,safety=state,age=0 if not inside and loss else 6)
            # Follow slot zero. Slot one does the physical stop.
            for packet in packets.values():
                packet[27]=0
            car=29+57
            lap=packets[2]
            lap[car+34]=2 if inside else 0
            lap[car+46]=int(inside)
            struct.pack_into("<H",lap,car+17,2000+loss)
            struct.pack_into("<H",lap,car+49,2300 if inside else 0)
            address=("127.0.0.1",app.state.udp.port)
            for key in (1,4,7,10,2):
                sender.sendto(packets[key],address)
            return wait_for(app.state.udp.snapshot,lambda s:s.get('cars') and s['uid']==str(uid)
                         and s['cars'][1]['pit']==inside and s['cars'][1]['gapMs']==2000+loss
                         and s['safety']==state)
        with TestClient(app):
            send(400,1,False,0,safety)
            send(400,2,True,0,safety)
            mid=send(400,3,True,4900,safety)
            assert mid['cars'][1]['accruedPitLossMs']==4900
            final=send(400,4,False,8700,safety)
            assert final['neutralPitLoss']==(8700,1) and final['pitLossSamples']==0
        with TestClient(app):
            loaded=send(410,1,False,0,safety)
            assert loaded['neutralPitLoss']==(8700,1)
            assert send(410,2,False,0,3-safety)['neutralPitLoss'] is None

@pytest.mark.skipif(__import__("sys").platform!="win32",reason="Windows file sharing")
def test_locked_manifest_keeps_recording_pit_through_exit(monkeypatch):
    monkeypatch.setenv("F125_UDP_PORT","0")
    with TestClient(app), socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
        address=("127.0.0.1",app.state.udp.port)
        drive_stop(2026,address,sender,812,1,False,2,True)
        path=wait_for(lambda: next(app.state.record_dir.glob("*/manifest.json"),None),bool)
        # Python opens without FILE_SHARE_DELETE on Windows, just like a catalog reader.
        with path.open("rb") as held:
            first=json.load(held)
            drive_stop(2026,address,sender,812,2,True,2)
            wait_for(app.state.udp.snapshot,lambda s:bool(s["recordError"]))
            drive_stop(2026,address,sender,812,3,False,1)
            wait_for(app.state.udp.snapshot,lambda s:s["pitComparisons"][-1][2]==1)
            wait_for(lambda:len(list(path.parent.glob("*.zst"))),lambda n:n>=first["chunks"]+2)
        wait_for(app.state.udp.snapshot,lambda s:s["recordError"] is None)
        manifest=json.loads(path.read_bytes())
        stop=manifest["stops"][-1]
        assert (stop["predicted"],stop["actual"])==(2,1)
        reader=f125_core.Replay(path.parent)
        assert reader.advance(stop["exitMs"])["pitComparisons"][-1][:3]==(7,2,1)
        assert app.state.udp.snapshot()["recordDropped"]==0

@pytest.mark.parametrize("safety", [0, 1, 2])
def test_work_classification_and_delay_isolation(monkeypatch, safety):
    monkeypatch.setenv("F125_UDP_PORT", "0")
    with TestClient(app), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sequence = 0

        def send(inside, damage, age, gap=2000, service=0, state=safety, experience=0):
            nonlocal sequence
            sequence += 1
            batch = calibration_packets(654, sequence, 3, lane=inside, gap=gap, service=service, safety=state)
            batch[1][724] = experience
            batch[10][29+46+28:29+46+34] = bytes(damage)
            batch[7][29+59+27] = age
            receiver = app.state.udp
            before = receiver.snapshot()["accepted"]
            for key in (1, 4, 7, 10, 2):
                sock.sendto(batch[key], ("127.0.0.1", receiver.port))
            return wait_for(receiver.snapshot, lambda snap: snap["accepted"] >= before+5)

        def visit(entry, exit_damage, service, total):
            pre = send(False, entry, 4)
            send(True, entry, 4)
            send(True, exit_damage, 0, service=service)
            after = send(False, exit_damage, 0, gap=total+2000)
            stop = list(after["pitWork"].values())[-1]
            assert stop["entryScenarios"] == pre["serviceForecast"]
            assert stop["tyreChanged"] and stop["safetyStates"] == [safety]
            return stop, after

        mild = [5, 4, 2, 3, 0, 0]
        fixed = [0, 0, 2, 3, 0, 0]
        stop, first = visit(mild, mild, 2500, 18000)
        assert stop["repairs"] == [] and not stop["serviceDelayed"]
        assert first["serviceForecast"][0][1:] == (18000, 1)
        stop, normal = visit(mild, fixed, 8000, 26000)
        assert stop["repairs"] == ["frontLeft", "frontRight"] and not stop["serviceDelayed"]
        assert normal["serviceForecast"][1][1:] == (26000, 1)
        # Me at +2s, P3 at +22s: one rival crosses only the wing threshold.
        assert [r[0] for r in send(False, mild, 3)["serviceForecast"]] == [2, 3]
        assert normal["serviceAverages"] == [(2500, 1), (8000, 1)]
        stop, short_delay = visit(mild, mild, 3400, 18400)
        assert stop["serviceVerdict"] == "suspectedDelay" and not stop["serviceIncluded"]
        assert short_delay["serviceForecast"][0][1:] == (18000, 1)
        for body, ms in ((mild, 7000), (fixed, 13000)):
            stop, slow = visit(mild, body, ms, 35000)
            assert stop["serviceDelayed"] and stop["measuredLossMs"] == 35000
            assert slow["serviceForecast"] == short_delay["serviceForecast"]
        stop, _ = visit(mild, [5,4,0,0,0,0], 8000, 27000)
        assert stop["repairs"] == ["rearWing","floor"] and stop["serviceDelayed"] is None
        isolated = send(False, mild, 4, state=(safety+1)%3)
        assert all(r[2]==0 for r in isolated["serviceForecast"])
        switched = send(False, mild, 4, experience=2)
        assert switched["serviceAverages"] == [None, None]
        original = send(False, mild, 4)
        assert original["serviceAverages"] == [(2500, 1), (8000, 1)]
    with TestClient(app), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        loaded = send(False, mild, 4)
        assert [r[1:] for r in loaded["serviceForecast"]] == [(18000,1),(26000,1)]
