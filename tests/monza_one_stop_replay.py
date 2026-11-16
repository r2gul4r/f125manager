"""Check the Monza M-to-H stop and flashbacks using only packets up to each timestamp."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f125_core import Replay
from live_timing import live_frame


def check(recording):
    replay = Replay(recording)

    def at(milliseconds):
        return live_frame(replay.advance(milliseconds), pit_ms=replay.pit_loss_ms)

    before = at(938795)
    assert before["lap"] == 10
    assert before["forecast"]["plans"][0]["stops"] == [{"lap": 12, "tyre": "H"}]
    exit_estimate = before["forecast"]["rejoins"][2]
    assert (exit_estimate["position"], exit_estimate["trafficAhead"]) == (1, [])
    assert exit_estimate["lossMs"] == 20363
    restoring = at(1079000)
    assert restoring["forecast"] is None and restoring["forecastWait"] == "Waiting for tyre history"
    restored = at(1081000)["forecast"]
    chosen = next(p for p in restored["plans"] if p["id"] == restored["recommended"])
    assert chosen["stops"] == [{"lap": 12, "tyre": "H"}]
    for milliseconds in (1170000, 1290000, 1350000, 1370000, 1450000):
        frame = at(milliseconds)
        assert frame["cars"][frame["player"]]["tyre"] == "H"
        if milliseconds == 1350000:
            assert not frame.get("forecast") and not frame["observedStints"]
            continue
        assert {"lap": 12, "tyre": "H"} in frame["observedStints"]
        forecast = frame["forecast"]
        assert forecast["recommended"] == "A" and forecast["plans"][0]["stops"] == []


if __name__ == "__main__":
    check(Path(sys.argv[1]))
    print("Monza replay passed: lap 12 hard, no second stop, flashback recovery.")
