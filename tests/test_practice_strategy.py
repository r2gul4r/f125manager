import json
from pathlib import Path

from practice_strategy import archived_laps, grid_setup, profile


def test_independent_player_pace_and_degradation():
    # Both personal laps are on the same set. A different driver, session,
    # surface or set must never contribute the other endpoint of a pair.
    rows = [
        ((1, 7, 2), (True, 17, 1, 0, 95000, 3.0)),
        ((1, 7, 3), (True, 17, 2, 0, 95200, 4.0)),
        ((1, 7, 4), (True, 17, 0, 0, 94000, None)),
        ((1, 7, 5), (True, 17, 1, 1, 98400, 1.0)),
        ((1, 6, 2), (False, 17, 0, 0, 97000, 2.0)),
        ((2, 6, 3), (False, 17, 1, 0, 90000, 2.0)),
    ]
    dry = profile(rows, 0)
    assert "kgPerLap" not in dry
    assert dry["tyres"]["M"]["paceMs"] == 95100
    assert dry["tyres"]["M"]["trendMs"] == 200
    assert dry["tyres"]["M"]["pairs"] == 1
    assert dry["tyres"]["M"]["wearPct"] == 3.5
    assert profile(rows, 1)["playerLaps"] == 0


def test_cooldown_is_excluded_from_pace_wear_and_trend():
    times = [90000, 90200, 110000, 111000, 90400, 90600]
    rows = [((1, 2, age+1), (True, 17, age, 0, ms, 10 if ms > 100000 else 3))
            for age, ms in enumerate(times)]
    evidence = profile(rows, 0)
    assert evidence["playerLaps"] == 4 and evidence["excludedLaps"] == 2
    assert evidence["tyres"]["M"]["wearPct"] == 3
    assert evidence["tyres"]["M"]["pairs"] == 2


def test_only_completed_fp_of_same_weekend(tmp_path, monkeypatch):
    raw = {"format": 2026, "track": 3, "seasonLink": 7, "weekendLink": 9}
    for name, end, kind in [
        ("past", 90, 1),
        ("other", 91, 1),
        ("future", 101, 2),
        ("race", 85, 15),
    ]:
        directory = tmp_path / name
        directory.mkdir()
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "uid": name,
                    "startedMs": 50,
                    "durationMs": end - 50,
                    "format": 2026,
                    "track": 3,
                    "sessionType": kind,
                    "packets": 20,
                }
            )
        )

    def read(path: Path, duration, packets):
        assert path.name in ("past", "other")
        return (2026, 3, 7, 9 if path.name == "past" else 10), [
            (True, 1, 3, 16, 0, 0, 95000, 4)
        ]

    monkeypatch.setattr("practice_strategy._read_session", read)
    assert [key[0] for key, _ in archived_laps(tmp_path, raw, 100)] == ["past"]


def test_dry_to_rain_uses_only_observed_compounds_and_available_sets():
    raw = {
        "weather": 0,
        "sessionType": 15,
        "player": 0,
        "cars": [
            {
                "slot": 0,
                "tyreSets": [(17, 0, True, 12, 0, True), (7, 0, True, 12, 8000, False)],
            }
        ],
        "weatherOutlook": [(5, 3, 80)],
    }
    frame = {"totalLaps": 10, "pitLossMs": 20000}
    assert not grid_setup(raw, frame, profile([], 0))["plans"]
    sample = {"paceMs": 95000, "trendMs": 100, "wearPct": 2, "medianAge": 1}
    dry, wet = {"tyres": {"M": sample}}, {"tyres": {"I": sample}}
    base = grid_setup(raw, frame, dry, {0: dry, 1: wet})
    assert base["plans"][0]["start"] == "M"
    assert base["plans"][0]["stops"] == [{"lap": 4, "tyre": "I"}]
    raw["cars"][0]["tyreSets"].pop()
    assert not grid_setup(raw, frame, dry, {0: dry, 1: wet})["plans"]
