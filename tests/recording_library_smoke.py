"""Replay each real archive without a UDP listener. Run with the recording root."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f125_core
from live_timing import live_frame
from recordings import analysis_view, catalog


def inspect(path, listed):
    manifest = json.loads(path.read_bytes())
    reader = f125_core.Replay(path.parent)
    end = reader.duration_ms
    midpoint = end // 2
    times = {0, midpoint, end, *range(0, end, 10000)}
    for stop in manifest["stops"]:
        for at in (stop["entryMs"], stop["exitMs"]):
            if at is not None:
                times.update(t for t in (at-1, at, at+1) if 0 <= t <= end)
    counts = Counter()
    flags = set()
    last_average = {}
    for ms in sorted(times):
        raw = reader.advance(ms)
        frame = live_frame(raw)
        if ms == midpoint:
            original = frame
        if not frame:
            continue
        counts["timing"] += 1
        cars = frame["cars"]
        assert len({c["code"] for c in cars}) == len(cars)
        flags.add(frame["flag"])
        counts["map"] += any(c["phase"] is not None for c in cars)
        counts["pit_forecast"] += frame["boxNowPosition"] is not None
        for s in frame["pitComparisons"]:
            assert s["entryMs"] <= ms and (s["exitMs"] is None or s["exitMs"] <= ms)
            assert s["actual"] is None or s["exitMs"] is not None
        forecast = frame["forecast"]
        if forecast:
            plans = forecast["plans"]
            assert [p["id"] for p in plans] == ["A", "B", "C"]
            position = cars[frame["player"]]["position"]
            assert forecast["recommended"] == min(plans, key=lambda p: (
                any(issue[3] in {"stock","weather"} for issue in p["tyreIssues"]),
                -sum(r < position for r in p["scenarioRanks"]), sum(p["scenarioRanks"]),
                max(p["scenarioRanks"]), p["lifeShortfall"], p["remainingMs"]))["id"]
            assert all(frame["lap"] <= p["stop"]["lap"] < frame["totalLaps"] and
                       p["remainingMs"] > 0 and 1 <= p["finish"][0] <= p["finish"][1] <= 22 for p in plans)
            counts["abc"] += 1
        for side, pace in frame["lapAnalysis"].items():
            if not pace or not pace["sampleLaps"]:
                last_average.pop(side, None)
                continue
            key = (frame["session"], pace["leader"], pace["follower"], pace["lap"], pace["sampleLaps"])
            if side in last_average and last_average[side][0] == key:
                assert pace["deltaMs"] == last_average[side][1]
            last_average[side] = (key, pace["deltaMs"])
            counts["lap_average"] += 1
    result = frame["pitComparisons"] if frame else []
    assert result == [{k: s[k] for k in row} for row, s in zip(result, listed["stops"], strict=True)]
    bahrain = {
        "1794655466089283-cab8d764d84f0aae": [(3, 8016, [0, 2], 21), (11, 8000, [0], 20)],
        "1794660248644479-bcd8c3d49cdcd06f": [(2, 8000, [0], 21)],
    }
    if path.parent.name in bahrain:
        assert [(s["lap"], s["serviceMs"], s["safetyStates"], s["actual"]) for s in result] == bahrain[path.parent.name]
        assert [s["serviceSafety"] for s in result] == [row[2][-1] for row in bahrain[path.parent.name]]
        assert all(s["tyreChanged"] and s["wingRepair"] and s["pitExperience"] == 1
                   and s["serviceVerdict"] == "normal" and s["serviceIncluded"]
                   for s in result)
        for stop in result:
            assert stop["lossIncluded"] == (stop["lap"] == 2)
            if stop["lossIncluded"]:
                assert stop["transitReferences"] == 8 and abs(stop["measuredLossMs"] - 25184) <= 15
    if path.parent.name == "1794711347679644-450152b3f1f6e1fc":
        stop = next(s for s in result if s["entryMs"] == 274005)
        assert stop["tyreChanged"] and not stop["repairs"] and stop["serviceMs"] == 2783
        assert stop["predicted"] == stop["actual"] == 21 and stop["lossIncluded"]
        assert stop["transitReferences"] == 12 and abs(stop["measuredLossMs"] - 19493) <= 15
        before = reader.advance(stop["entryMs"]-1)
        assert before["pitLossSamples"] == 0
        after = reader.advance(stop["exitMs"])
        assert (after["pitLossSamples"], after["pitLossMs"]) == (1, stop["measuredLossMs"])
        reader.advance(end)
        held = f125_core.Replay.for_handoff(path.parent)
        pre = held.advance(stop["entryMs"]-1)
        assert [row[2] for row in pre["serviceForecast"]] == [0, 1]
        frame_now = live_frame(held.advance(end))
        assert [row[1:] for row in frame_now["serviceForecast"]] == [(19486, 1), (25184, 1)]
        assert frame_now["serviceAverages"] == [(2783, 1), (8000, 2)]
        assert frame_now["pitComparisons"][-1]["recordedScenarios"] == stop["recordedScenarios"]
    for s in listed["stops"]:
        service = next((v for v in raw["pitService"] if v[0] == s["entryMs"]), None)
        if service and service[2]:
            assert s.get("wingRepair") and s.get("serviceMs") == service[1]
    for stop in result:
        pair = stop.get("entryScenarios")
        if pair is None or stop["exitMs"] is None:
            continue
        prefix = f125_core.Replay(path.parent)
        assert prefix.advance(stop["entryMs"]-1)["serviceForecast"] == pair
        entered = live_frame(prefix.advance(stop["entryMs"]))["pitComparisons"][-1]
        assert entered["entryScenarios"] == pair and entered["actual"] is None
        assert entered["damageOut"] is None and entered["tyreChanged"] is None
        exited = live_frame(prefix.advance(stop["exitMs"]))["pitComparisons"][-1]
        assert exited["entryScenarios"] == pair and exited["actual"] == stop["actual"]
    trace = analysis_view(reader.analysis())
    assert live_frame(reader.advance(midpoint)) == original, (path.parent.name, midpoint)
    print(path.parent.name, "samples", len(times), dict(counts), "flags", sorted(flags),
          "laps", len(trace["laps"]), "telemetry", len(trace["samples"]), "final stops", result, flush=True)


if __name__ == "__main__":
    root = Path(sys.argv[1])
    paths = sorted(root.glob("*/manifest.json"))
    if not paths:
        sys.exit("No recordings")
    records = {r["id"]: r for r in catalog(root)}
    for path in paths:
        inspect(path, records[path.parent.name])
