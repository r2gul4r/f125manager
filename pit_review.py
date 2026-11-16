"""Compare dashboard samples with the observed exit on the retained race timeline."""
import json
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

import f125_core
from live_timing import driver_codes, exit_passage, pit_laps
from pit_diagnosis import diagnose


class Exit(BaseModel):
    position: int = Field(ge=1, le=24)
    before: str | None = Field(max_length=8)
    after: str | None = Field(max_length=8)
    aheadGapMs: int | None = Field(ge=0)
    behindGapMs: int | None = Field(ge=0)
    lossMs: int | None = Field(default=None, ge=0)
    penaltyMs: int | None = Field(default=None, ge=0)
    rivalMargins: list[tuple[str, int]] | None = Field(default=None, max_length=24)
    lapPaceMs: list[tuple[str,int]] | None = Field(default=None,max_length=3)
    validation: tuple[bool,int,int|None,int|None] | None = None


class Sample(BaseModel):
    at: int = Field(ge=0)
    branch: int = Field(ge=0)
    tick: int = Field(ge=0)
    lap: int = Field(ge=1, le=255)
    target: int = Field(ge=1, le=255)
    visible: bool
    basis: int = Field(ge=1, le=255)
    held: bool
    exit: Exit


def save_samples(directory: Path, samples: list[Sample]):
    rows = [(s.at, s.branch, s.tick, s.lap, s.target, int(s.visible), s.basis, int(s.held), s.exit.model_dump_json())
            for s in samples if s.target >= s.lap and (s.visible or s.target - s.lap <= 3)]
    if not rows:
        return
    with closing(sqlite3.connect(directory / "dashboard-exits.sqlite3", timeout=5)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS samples (
            at INTEGER, branch INTEGER, tick INTEGER, lap INTEGER, target INTEGER, visible INTEGER,
            basis INTEGER, held INTEGER, prediction TEXT, PRIMARY KEY(target,lap,branch,at,visible)) WITHOUT ROWID""")
        db.execute("CREATE INDEX IF NOT EXISTS samples_source ON samples(lap,at)")
        db.executemany("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?,?,?)", rows)


@lru_cache(maxsize=32)
def recorded_passages(directory, duration):
    return f125_core.Replay(directory).advance(duration).get("exitPassages", {})


@lru_cache(maxsize=128)
def stop_observations(directory, entry, exit_ms):
    reader = f125_core.Replay(directory)
    raw = reader.advance(entry)
    # A rewind can keep an earlier lap. A second rewind can also invalidate
    # part of that already retained prefix.
    branch = raw.get("timingBranch")
    cutoff = raw.get("timingFrame", 0)
    limits = {branch: cutoff} if branch is not None else {}
    for old, target in reversed(raw.get("rewindLimits", ())):
        cutoff = min(cutoff, target)
        limits[old] = cutoff
    cars = {c["slot"]:c for c in raw.get("cars", ())}
    raw = reader.advance(exit_ms)
    codes=driver_codes(raw.get("cars", []))
    pitted = [codes[c["slot"]] for c in raw.get("cars", ()) if c["slot"] in cars and c["slot"]!=raw["player"]
              and (c["pitStops"]>cars[c["slot"]]["pitStops"] or (c["pit"] and not cars[c["slot"]]["pit"]))]
    ranks={codes[c["slot"]]:c["position"] for c in raw.get("cars",[]) if c["position"] and c["result"] in (2,3)}
    clean={}
    for car in raw.get("cars",[]):
        exclude=pit_laps(raw,car) | set(car.get("slowLaps",()))
        clean[codes[car["slot"]]]={n:ms for n,(ms,_,valid) in enumerate(car.get("history",[]),1)
                                    if n<car["lap"] and ms and valid&1 and n not in exclude}
    return limits, codes, pitted, ranks, clean, codes.get(raw.get("player"))


def comparison(directory, stops, duration):
    db_path = directory / "dashboard-exits.sqlite3"
    result = []
    last_exit = -1
    for stop in sorted(stops, key=lambda s: s["entryMs"]):
        entry, exited, lap = stop["entryMs"], stop["exitMs"], stop["lap"]
        if exited is None:
            continue
        limits, codes, pitted, ranks, clean, player = stop_observations(directory, entry, exited)
        actual = exit_passage(recorded_passages(directory, duration).get(exited), codes, live=False)
        if actual is None and stop.get("actual"):
            actual = {"position":stop["actual"], "before":None, "after":None,
                      "aheadGapMs":None, "behindGapMs":None,"neighboursKnown":False}
        by_lap = {}
        if db_path.is_file():
            with closing(sqlite3.connect(db_path)) as db:
                rows = db.execute("""SELECT lap,branch,tick,at,visible,basis,held,prediction,target FROM samples
                    WHERE (target=? OR visible=1) AND lap BETWEEN ? AND ? AND at>? AND at<?
                    ORDER BY visible DESC, at DESC, (target=?) DESC, target""", (lap, lap-3, lap, last_exit, entry, lap))
                for source, branch, tick, at, visible, basis, held, prediction, target_lap in rows:
                    if source not in by_lap and branch in limits and tick <= limits[branch]:
                        by_lap[source] = {**json.loads(prediction), "at":at, "visible":bool(visible),
                                          "basis":basis, "held":bool(held), "target":target_lap}
        forecasts=[by_lap.get(lap-offset) for offset in (3,2,1,0)]
        result.append({"lap":lap, "entryMs":entry, "actual":actual, "forecasts":forecasts,
                       "review":diagnose(stop,forecasts,actual,pitted,ranks,clean,player)})
        last_exit = exited
    return result
