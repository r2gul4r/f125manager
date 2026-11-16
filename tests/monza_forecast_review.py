"""Score chronological Monza replay predictions against later observations, once per lap or stop."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f125_core import Replay
from live_timing import PlanDisplay, live_frame, pit_laps, running_pace


def review(path):
    manifest = json.loads((path / "manifest.json").read_bytes())
    stops = {s["entryMs"]: s for s in manifest["stops"] if s.get("exitMs") is not None}
    replay = Replay(path)
    display = PlanDisplay()
    # The manifest supplies scoring timestamps only. No exit result goes into live_frame.
    snapshots, recommendations, midlaps, completed = {}, {}, {}, {}
    coverage, waits = Counter(), Counter()
    stop_times = {ms for entry, stop in stops.items() for ms in
                  (entry - 1, stop["exitMs"], min(replay.duration_ms, stop["exitMs"] + 4000))}
    times = set(range(0, replay.duration_ms, 1000)) | {replay.duration_ms} | stop_times
    for ms in sorted(times):
        raw = replay.advance(ms)
        frame = live_frame(raw, pit_ms=replay.pit_loss_ms)
        if not frame or frame["player"] < 0:
            continue
        me = next(c for c in raw["cars"] if c["slot"] == raw["player"])
        epoch, lap = raw["epoch"], me["lap"]
        fc = frame["forecast"]
        display.update(frame, raw)
        key = epoch, lap
        if frame["canPlan"] and frame["mode"] == "race" and ms % 1000 == 0:
            state = "fresh" if fc else "retained" if frame.get("previousPlans") else "waiting"
            coverage[state] += 1
            if not fc:
                waits[frame["forecastWait"]] += 1
        if fc:
            assert [plan["id"] for plan in fc["plans"]] == ["A", "B", "C"]
            for plan in fc["plans"]:
                schedule = [s["lap"] for s in plan["stops"]]
                assert schedule == sorted(set(schedule))
                assert all(lap <= at <= frame["totalLaps"] for at in schedule), (ms, lap, schedule)
        if fc and key not in recommendations:
            plan = next(p for p in fc["plans"] if p["id"] == fc["recommended"])
            recommendations[key] = (ms, [(s["lap"], s["tyre"]) for s in plan["stops"]],
                                    plan["scenarioRanks"][2])
        excluded = pit_laps(raw, me) | set(me.get("slowLaps", ()))
        fraction = (me.get("distance") or 0) / max(1, raw["length"])
        checkpoint = next((q for q in (.25, .5, .75) if q <= fraction < q + .05), None)
        marker = epoch, lap, checkpoint
        if checkpoint and marker not in midlaps and lap > 1 and not me["pit"] and lap not in excluded:
            estimate, _ = running_pace(me, raw["length"], pit_laps(raw, me), raw["sectorStarts"])
            if estimate:
                midlaps[marker] = estimate
        for n, (duration, _, flags) in enumerate(me.get("history", ()), 1):
            if n < lap and duration and flags & 1 and n not in excluded:
                completed[epoch, n] = duration
            elif n in excluded or not flags & 1:
                completed.pop((epoch, n), None)
        if ms in stop_times:
            i = frame["player"]
            following = frame["cars"][i+1] if i+1 < len(frame["cars"]) else {}
            snapshots[ms] = (epoch, lap, me["position"], following.get("code"), following.get("intervalMs"),
                             fc["tyreExits"][0] if fc else None)
        if ms == replay.duration_ms:
            final, stints = (epoch, me["position"], me["result"]), frame["observedStints"]
    errors = defaultdict(list)
    for (epoch, lap, checkpoint), estimate in midlaps.items():
        if (epoch, lap) in completed:
            errors[checkpoint].append(estimate - completed[epoch, lap])
    print("eligible 1s samples", coverage, "fresh calculation unavailable", waits)
    print("finish (epoch, position, result), tyre changes", final, stints)
    for checkpoint, signed in sorted(errors.items()):
        print("lap fraction, n, MAE ms, median absolute ms, bias ms", checkpoint, len(signed),
              round(mean(map(abs, signed))), round(median(map(abs, signed))), round(mean(signed)))
    print("first available recommendation per epoch/lap", recommendations)
    for entry, s in stops.items():
        print("stop", s["lap"], "recorded forecast", s.get("predicted"), "service", s.get("serviceMs"),
              "measured loss", s.get("measuredLossMs"))
        for ms in (entry-1, s["exitMs"], s["exitMs"]+4000):
            print(ms, snapshots.get(ms))
    matching = [v[2] for (ep, lap), v in recommendations.items() if ep == final[0]
                and v[1] == [(s["lap"], s["tyre"]) for s in stints if s["lap"] >= lap]]
    print("final epoch matched schedules, central finish positions", matching)


if __name__ == "__main__":
    review(Path(sys.argv[1]))

