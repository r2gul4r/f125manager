import struct

import pytest
from fastapi.testclient import TestClient

import f125_core
from server import app, timing_snapshot


@pytest.mark.parametrize("format_id", [2025, 2026])
def test_header_bridge(format_id):
    header = struct.pack(
        "<HBBBBBQfIIBB", format_id, 25, 1, 0, 1, 2, 8123, 0.0, 3, 7, 1, 255
    )
    assert f125_core.read_header(header) == (format_id, 2, 8123, 7)
    with pytest.raises(ValueError):
        f125_core.read_header(header[:-1])


def test_tower_keeps_player_slot_after_pit():
    first = timing_snapshot(0)
    after = timing_snapshot(47)
    assert first["player"] == after["player"]
    assert first["cars"][first["player"]]["position"] == 8
    assert after["cars"][after["player"]]["position"] == 7


def test_stints_follow_the_mock_stop_even_on_mid_race_join():
    def driver(seconds, code):
        return next(c for c in timing_snapshot(seconds)["cars"] if c["code"] == code)

    before = driver(47.9, "ALO")
    after = driver(48, "ALO")
    assert before["tyre"] == "S" and after["tyre"] == "H"
    assert after["stints"] == [*before["stints"], {"tyre":"H", "laps":0}]
    for c in timing_snapshot(59)["cars"]:
        assert sum(s["laps"] for s in c["stints"]) == 20
        assert c["stints"][-1] == {"tyre":c["tyre"], "laps":c["age"]}
    assert driver(108,"ALO")["stints"] == driver(0,"ALO")["stints"]


def test_minis_progress_per_car_reset_and_freeze():
    def leader(at):
        return timing_snapshot(at)["cars"][0]

    for at in (0, 1, 7, 9, 10):
        c = leader(at)
        assert len(c["minis"]) == int(c["phase"] * 24) or (len(c["minis"]) == 24 and c["phase"] < 1/24)
        assert sum(t is not None for t in c["liveSectors"]) == len(c["minis"]) // 8
    assert len(leader(1)["minis"]) > len(leader(0)["minis"])
    assert len(leader(11)["minis"]) < len(leader(7)["minis"])
    assert next(c for c in timing_snapshot(103)["cars"] if c["retired"])["minis"] == next(
        c for c in timing_snapshot(107)["cars"] if c["retired"])["minis"]
    assert all(not c["minis"] and c["liveSectors"] == [None]*3 for c in timing_snapshot(0,"grid")["cars"])


def test_mock_ws_receives_fresh_frames():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["native_core"] == "f125_core"
        with client.websocket_connect("/ws/demo") as socket:
            first, second = socket.receive_json(), socket.receive_json()
            assert len(first["cars"]) == 24
            assert [car["code"] for car in first["cars"][-2:]] == ["KIM", "SEO"]
            assert all(sum(car["sectors"]) == car["lastMs"] for car in first["cars"])
            assert first["cars"] != second["cars"]

def test_event_history_advances_once_and_resets_between_races():
    before = timing_snapshot(47.9)["events"]
    after = timing_snapshot(48)["events"]
    assert after[1:] == before
    assert timing_snapshot(48.1)["events"] == after
    restarted = timing_snapshot(108)["events"]
    assert {event["id"] for event in after}.isdisjoint(event["id"] for event in restarted)


def test_event_log_keeps_changes_and_skips_repeated_status_reports():
    start = timing_snapshot(0)["events"]
    assert len(start) >= 20
    before = timing_snapshot(29)["events"]
    assert timing_snapshot(31)["events"] == before  # VER is still leading.
    events = timing_snapshot(107)["events"]
    assert not {"랩 완료", "속도 유지", "대열 유지", "선두 유지"} & {e["label"] for e in events}
    assert [e["driver"] for e in reversed(events) if e["label"] == "선두 진입"] == ["NOR", "VER"]
    assert sum(e["label"] == "그린 플래그" for e in events) == 4


def test_event_details_are_frozen_at_event_time():
    at_entry = timing_snapshot(36)["events"][0]
    assert at_entry["label"] == "피트 진입"
    assert "소프트" in at_entry["detail"]
    later = timing_snapshot(72)["events"]
    assert next(event for event in later if event["id"] == at_entry["id"]) == at_entry
    assert all(event["detail"].strip() for event in later)


def test_driver_rulings_preserve_recipient_kind_and_seconds():
    events = timing_snapshot(107)["events"]
    rulings = [e for e in reversed(events) if "ruling" in e]
    assert [(e["driver"], e["ruling"], e["seconds"]) for e in rulings] == [
        ("HUL", "drive_through", 0), ("YOU", "time", 5), ("YOU", "black_white", 0), ("GAS", "black_white", 0),
        ("GAS", "time", 5), ("YOU", "time", 3), ("KIM", "stop_go", 10),
    ]
    assert len({e["id"] for e in events}) == len(events)
    assert all(e["detail"] for e in rulings)


def test_driver_penalties_survive_frames_until_each_is_served():
    def pending(seconds):
        return {car["code"]: [(p["kind"], p["seconds"]) for p in car["pendingPenalties"]]
                for car in timing_snapshot(seconds)["cars"]}

    assert pending(44)["YOU"] == [("time", 5)]
    assert pending(84)["YOU"] == [("time", 5), ("time", 3)]
    assert pending(93)["YOU"] == [("time", 3)]
    assert pending(93)["GAS"] == [("time", 5)]
    assert pending(96)["GAS"] == []
    assert pending(102)["YOU"] == []
    assert pending(102)["KIM"] == [("stop_go", 10)]
    assert pending(105)["KIM"] == []
    assert pending(108) == pending(0)
    assert any(e["label"] == "페널티 이행" for e in timing_snapshot(105)["events"])

def test_global_and_local_flags_clear_and_reset():
    for seconds, flag, sectors in [(5, "TRACK CLEAR", []), (6, "YELLOW", [2]),
                                   (14, "TRACK CLEAR", []), (32, "YELLOW", []),
                                   (38, "RED", []), (46, "TRACK CLEAR", []),
                                   (54, "SC", []), (72, "VSC", []), (108, "TRACK CLEAR", [])]:
        frame = timing_snapshot(seconds)
        assert (frame["flag"], frame["yellowSectors"]) == (flag, sectors)


def test_retirement_is_per_driver_and_resets_with_the_mock_race():
    def cars(at):
        return {car["code"]: car for car in timing_snapshot(at)["cars"]}

    assert cars(40)["ALO"]["pit"] and not cars(40)["ALO"]["retired"]
    assert not cars(102)["ALO"]["retired"]
    stopped = cars(103)
    assert [c for c in stopped if stopped[c]["retired"]] == ["ALO"]
    assert stopped["ALO"]["speed"] == 0
    assert stopped["ALO"]["phase"] == cars(107)["ALO"]["phase"]
    assert timing_snapshot(103)["events"][0]["label"] == "리타이어"
    assert not cars(108)["ALO"]["retired"]
