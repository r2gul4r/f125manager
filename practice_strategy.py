"""Pre-start policy using completed FP recordings from this Grand Prix."""

import json
from collections import defaultdict
from functools import lru_cache
from statistics import median

import f125_core
from live_timing import COMPOUNDS, surface_for


@lru_cache(maxsize=32)
def _read_session(directory, duration, packets):
    reader = f125_core.Replay(directory)
    raw = reader.advance(duration)
    identity = tuple(
        raw.get(k) for k in ("format", "track", "seasonLink", "weekendLink")
    )
    return identity, raw.get("practiceLaps", ())


def archived_laps(root, raw, cutoff):
    identity = tuple(
        raw.get(k) for k in ("format", "track", "seasonLink", "weekendLink")
    )
    result = {}
    if not identity[-1]:
        return []
    for path in sorted(root.glob("*/manifest.json")):
        try:
            data = json.loads(path.read_bytes())
            if (
                data["sessionType"] not in range(1, 5)
                or data["track"] != raw["track"]
                or data["format"] != raw["format"]
                or data["startedMs"] + data["durationMs"] > cutoff
            ):
                continue
            key, rows = _read_session(path.parent, data["durationMs"], data["packets"])
            if key == identity:
                for own, slot, lap, compound, age, surface, ms, wear in rows:
                    result[data["uid"], slot, lap] = (
                        own,
                        compound,
                        age,
                        surface,
                        ms,
                        wear,
                    )
        except (OSError, ValueError, KeyError):
            continue
    return list(result.items())


def profile(rows, surface):
    clean = {key: r for key, r in rows if r[3] == surface}
    # UDP has no practice programme result. Require repeated pace on the same set.
    # Compare within one driver's session and compound so AI pace and changing
    # conditions in a different session cannot disqualify the player's laps.
    pairs = defaultdict(list)
    for (uid, slot, lap), row in clean.items():
        prev = clean.get((uid, slot, lap - 1))
        if prev and prev[:2] == row[:2] and prev[2] + 1 == row[2]:
            slower, faster = max(prev[4], row[4]), min(prev[4], row[4])
            if slower <= faster * 1.04:
                pairs[uid, slot, row[1]].append((lap - 1, lap, slower))
    selected = {}
    paired = set()
    for (uid, slot, _), runs in pairs.items():
        limit = min(slower for _, _, slower in runs) * 1.04
        for first, second, slower in runs:
            if slower <= limit:
                paired.add((uid, slot, second))
                for lap in (first, second):
                    key = uid, slot, lap
                    selected[key] = clean[key]

    def prefer(values):
        personal = [v for own, v in values if own]
        return (
            (personal, "Player")
            if personal
            else ([v for _, v in values], "Field" if values else "Unavailable")
        )

    tyres = {}
    for code, tyre in COMPOUNDS.items():
        bucket = [(k, r) for k, r in selected.items() if r[1] == code]
        if not bucket:
            continue
        laps, source = prefer([(r[0], r[4]) for _, r in bucket])
        changes = []
        for (uid, slot, lap), row in bucket:
            if (uid, slot, lap) in paired:
                prev = selected[uid, slot, lap - 1]
                changes.append((row[0], row[4] - prev[4]))
        slopes, slope_source = prefer(changes)
        wear, wear_source = prefer(
            [(r[0], r[5]) for _, r in bucket if r[5] is not None]
        )
        ages = [r[2] for _, r in bucket if source == "Field" or r[0]]
        tyres[tyre] = {
            "paceMs": round(median(laps)),
            "laps": len(laps),
            "source": source,
            "trendMs": round(median(slopes)) if slopes else None,
            "pairs": len(slopes),
            "trendSource": slope_source,
            "medianAge": median(ages),
            "wearPct": round(median(wear), 2) if wear else None,
            "wearLaps": len(wear),
            "wearSource": wear_source,
        }
    return {
        "tyres": tyres,
        "basis": "Pace-matched consecutive FP telemetry laps",
        "excludedLaps": len(clean) - len(selected),
        "playerLaps": sum(r[0] for r in selected.values()),
        "fieldLaps": sum(not r[0] for r in selected.values()),
    }


@lru_cache(maxsize=64)
def schedules(total, inventory, metrics, surfaces, pit_ms, two_dry):
    """Cheapest feasible schedule for each starting compound. Each set is consumed once."""
    stock = defaultdict(list)
    for tyre, life, delta in inventory:
        stock[tyre].append((life, delta))
    for sets in stock.values():
        sets.sort(reverse=True)
    kinds = tuple(sorted(stock))
    rates = {t: (pace, slope) for t, pace, slope in metrics}

    def suitable(t, surface):
        return t in ("SMH" if surface == 0 else "I" if surface == 1 else "W")

    @lru_cache(None)
    def best(at, used, first):
        if at == total:
            if two_dry and sum(v > 0 for v in used) < 2:
                return None
            return 0, ()
        if sum(used) >= 4:
            return None
        winner = None
        for i, t in enumerate(kinds):
            if first and t != first or used[i] >= len(stock[t]):
                continue
            life, _ = stock[t][used[i]]
            new = list(used)
            new[i] += 1
            pace, slope = rates[t]
            for length in range(1, min(life, total - at) + 1):
                if not suitable(t, surfaces[at + length - 1]):
                    break
                if (
                    at + length == total - 1
                ):  # Dashboard stop laps are strictly before the finish lap.
                    continue
                rest = best(at + length, tuple(new), "")
                if rest:
                    cost = (
                        length * pace
                        + slope * length * (length - 1) // 2
                        + (pit_ms if at else 0)
                        + rest[0]
                    )
                    candidate = cost, ((at + 1, t), *rest[1])
                    if winner is None or candidate < winner:
                        winner = candidate
        return winner

    plans = []
    for tyre in kinds:
        row = best(0, (0,) * len(kinds), tyre)
        if row:
            cost, stints = row
            plans.append(
                {
                    "start": tyre,
                    "stops": [{"lap": n, "tyre": t} for n, t in stints[1:]],
                    "modelMs": cost,
                }
            )
    return sorted(plans, key=lambda p: p["modelMs"])


def grid_setup(raw, frame, evidence, by_surface=None):
    me = next(c for c in raw["cars"] if c["slot"] == raw["player"])
    total = frame["totalLaps"]
    data = dict(evidence, plans=[], inventoryKnown=bool(me.get("tyreSets")))
    if not 1 < total <= 100 or raw["weather"] not in range(6):
        return data
    surface = surface_for(raw["weather"])
    profiles = by_surface or {surface: evidence}
    rates = []
    inventory = []
    for code, wear, available, life, delta, fitted in me.get("tyreSets", ()):
        tyre = COMPOUNDS.get(code)
        if not tyre or not life or not (available or fitted):
            continue
        target_surface = 1 if tyre == "I" else 2 if tyre == "W" else 0
        sample = profiles.get(target_surface, {}).get("tyres", {}).get(tyre)
        if not sample or sample["trendMs"] is None:
            continue
        if rate := sample["wearPct"]:
            life = min(life, int((100 - wear) / rate))
        inventory.append((tyre, life, delta))
        slope = max(0, sample["trendMs"])
        rates.append(
            (tyre, round(sample["paceMs"] - slope * sample["medianAge"]), slope)
        )
    if not inventory or not evidence["tyres"]:
        return data
    base = median(v["paceMs"] for v in evidence["tyres"].values())
    surfaces = [surface] * total
    for minutes, weather, _ in sorted(raw.get("weatherOutlook", ())):
        if minutes > 0 and weather in range(6):
            at = max(1, round(minutes * 60000 / base))
            surfaces[at:] = [surface_for(weather)] * max(0, total - at)
    # A short sprint can use a single dry compound.
    two_dry = raw["sessionType"] in (15, 16, 17) and total > 5 and not any(surfaces)
    data["plans"] = schedules(
        total,
        tuple(inventory),
        tuple(sorted(set(rates))),
        tuple(surfaces),
        frame["pitLossMs"],
        two_dry,
    )
    return data
