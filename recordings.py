"""Recording catalog and playback; Rust owns raw files, timestamps and the race reducer."""

import asyncio
import json
import re
from functools import lru_cache
from pathlib import Path
from time import monotonic

from fastapi import WebSocketDisconnect

import f125_core
from demo_strategy import Plan
from gp_advisor import AdvisorView
from live_timing import SESSION, PlanDisplay, live_frame, pit_comparisons


def analysis_view(data):
    raw = data["frame"]
    player = next((c for c in raw.get("cars", []) if c["slot"] == raw.get("player")), None)
    laps = []
    if player and not raw["spectating"]:
        laps = [{"lap":n, "ms":ms, "sectors":sectors, "valid":bool(valid&1)}
                for n,(ms,sectors,valid) in enumerate(player.get("history", []),1)
                if ms and n < player["lap"]]
    return {"session":str(raw.get("uid"))+"/"+str(raw.get("epoch")), "length":raw.get("length"),
            "laps":laps, "samples":data["samples"] if player and not raw["spectating"] else []}


@lru_cache(maxsize=4)
def recording_analysis(directory, manifest_version):
    return analysis_view(f125_core.Replay(directory).analysis())


@lru_cache(maxsize=32)
def replay_stop_details(directory, epoch, stop_times):
    # Within an epoch the retained branch changes only at pit entry/exit.
    # Catalog refreshes while driving can therefore reuse this replay.
    reader = f125_core.Replay(directory)
    raw = reader.advance(reader.duration_ms)
    return pit_comparisons(raw)


def catalog_stops(directory, data):
    stops = data["stops"]
    current = {s["entryMs"]: s for s in stops if s["epoch"] == data["epoch"]}
    if not stops:
        return []
    times = tuple((s["entryMs"], s["exitMs"]) for s in stops)
    try:
        details = replay_stop_details(directory, data["epoch"], times)
    except (OSError, ValueError):
        # Keep indexed results visible even if an archived chunk cannot be decoded.
        return list(current.values())
    by_entry = {s["entryMs"]: s for s in stops}
    return [{**{k:v for k,v in by_entry.get(row["entryMs"], {}).items() if k not in ("scenarios","profile")}, **row} for row in details]


def catalog(root: Path):
    records = []
    for file in root.glob("*/manifest.json"):
        if not re.fullmatch(r"\d+-[0-9a-f]{16}", file.parent.name):
            continue
        try:
            data = json.loads(file.read_bytes())
            if data["id"] != file.parent.name or data["version"] not in (1, 2, 3, 4, 5, 6, 7, 8):
                continue
            data["stops"] = catalog_stops(file.parent, data)
            for key in ("seedLosses","neutralSeeds","fieldLosses","qualifiedFieldLosses","workSeeds","observationSeeds","fieldObservations"):
                data.pop(key,None)
            # A separately captured live result can survive a gap in the raw recording.
            # Keep its live receiver clock out of the replay timeline.
            evidence=file.with_name("observed-stops.json")
            if evidence.is_file():
                try:
                    saved=json.loads(evidence.read_bytes())
                    if saved["recording"]==data["id"] and saved["session"]==f'{data["uid"]}/{data["epoch"]}':
                        data["observedStops"]=saved["stops"]
                except (KeyError,ValueError,OSError):
                    pass
            kind = data["sessionType"]
            records.append(
                {
                    **data,
                    "sessionName": SESSION[kind]
                    if isinstance(kind, int) and 0 <= kind < len(SESSION)
                    else "Session",
                }
            )
        except (KeyError, ValueError, OSError):
            continue
    return sorted(records, key=lambda record: record["startedMs"], reverse=True)


def restore_plan_preview(reader, ms, target):
    """Recover a read-only Rust preview on a seek, from earlier packets only."""
    display = PlanDisplay()
    try:
        # Read consecutive blocks, newest first. A long gap or pit visit can
        # outlast one block. Replay the suffix before returning so a tyre change
        # or completed visit still invalidates the recovered preview.
        end = ms
        while end > 0:
            start = max(0, end - 120_000)
            older_branch = False
            found = False
            for at in range(start, end, 1000):
                raw = reader.advance(at)
                if (raw.get("uid"), raw.get("epoch")) != target:
                    older_branch = True
                    continue
                frame = live_frame(raw, pit_ms=reader.pit_loss_ms)
                display.update(frame, raw)
                found = found or bool(frame and frame["forecast"])
            if found:
                for at in range(end, ms, 1000):
                    raw = reader.advance(at)
                    display.update(live_frame(raw, pit_ms=reader.pit_loss_ms), raw)
                break
            if older_branch:
                break
            display = PlanDisplay()
            end = start
    finally:
        reader.advance(ms)
    return display


async def playback(socket, root, recording, subscribers, wheel,service):
    origin = socket.headers.get("origin")
    if (
        origin and origin.split("://", 1)[-1] != socket.headers.get("host")
    ) or not re.fullmatch(r"\d+-[0-9a-f]{16}", recording):
        await socket.close(code=1008)
        return
    await socket.accept()
    queue = asyncio.Queue(64)
    subscribers.add(queue)
    advisor = AdvisorView(service, replay=True)
    plan = None
    selected_label = None
    notice = ""
    started = int(recording.split("-")[0])//1000
    try:
        reader = await asyncio.to_thread(f125_core.Replay, root / recording)
        duration = reader.duration_ms
        cursor = 0.0
        speed = 1
        previous = monotonic()
        frame = None
        rendered = -1
        displayed = PlanDisplay()
        seeking = False
        identity = None
        while True:
            now = monotonic()
            cursor = min(duration, cursor + (now - previous) * 1000 * speed)
            previous = now
            ms = int(cursor)
            if rendered != ms:
                raw = await asyncio.to_thread(reader.advance, ms)
                rendered = ms
            branch = (raw.get("uid"), raw.get("epoch"))
            if identity is not None and identity != branch:
                advisor.reset()
                plan, selected_label, notice = None, None, ""
            identity = branch
            await advisor.prepare(raw,root,started)
            frame = advisor.render(raw, pit_ms=reader.pit_loss_ms, stamp=started+ms)
            if seeking and frame and frame["isRace"] and frame["mode"] == "race" and not frame["forecast"]:
                displayed = await asyncio.to_thread(restore_plan_preview, reader, ms, branch)
            seeking = False
            displayed.update(frame, raw)
            if frame:
                frame.update(source="Replay",token=f'replay/{recording}/{frame["session"]}/{frame["lap"]}/{advisor.version}',
                             selectedPlan=selected_label,notice=notice,plan=plan.wire() if plan else {"start":frame["cars"][frame["player"]]["tyre"] if frame["player"]>=0 else None,"stops":[]})
            keys = [queue.get_nowait() for _ in range(queue.qsize())]
            if frame:
                frame["wheel"] = {
                    "keys": keys,
                    "device": wheel.description(),
                    "bindings": {},
                }
            await socket.send_json(
                {
                    "status": "Replay",
                    "frame": frame,
                    "wheelKeys": keys,
                    "playback": {
                        "ms": ms,
                        "duration": duration,
                        "speed": speed if ms < duration else 0,
                    },
                }
            )
            try:
                cmd = await asyncio.wait_for(socket.receive_json(), timeout=0.1)
            except TimeoutError:
                continue
            if isinstance(cmd, dict) and cmd.get("type") in ("askCodex","applyCodex"):
                try:
                    plan = advisor.command(cmd,raw,frame,plan,started+ms)
                    notice = advisor.message
                except ValueError as exc:
                    notice = str(exc)
            if isinstance(cmd, dict) and cmd.get("type") == "confirm" and frame and frame["canPlan"] and cmd.get("token")==frame["token"]:
                try:
                    choice = next((p for p in (frame.get("forecast") or {}).get("plans",()) if p["id"]==cmd.get("planId")),None)
                    if not choice or choice.get("codexExpired") or choice["stops"]!=cmd.get("stops"):
                        raise ValueError("현재 재생 시점의 플랜을 다시 선택해")
                    plan = (plan or Plan(frame["plan"]["start"],())).confirm(cmd,frame["lap"],frame["totalLaps"],True,not choice["stops"])
                    selected_label = choice["id"]
                    notice = ""
                except (TypeError,ValueError) as exc:
                    notice = str(exc)
            if isinstance(cmd, dict) and cmd.get("type") == "playback":
                if type(cmd.get("ms")) is int:
                    cursor = max(0, min(duration, cmd["ms"]))
                    seeking = cursor != rendered
                    if cursor < rendered:
                        displayed = PlanDisplay()
                        advisor.reset()
                        plan = None
                        selected_label = None
                        notice = ""
                if cmd.get("speed") in (0, 1, 4, 16):
                    speed = int(cmd["speed"])
                previous = monotonic()
    except (OSError, ValueError) as exc:
        await socket.send_json(
            {"status": "Replay error", "error": str(exc), "frame": None}
        )
        await socket.close(code=1000)
    except WebSocketDisconnect:
        pass
    finally:
        advisor.reset()
        subscribers.discard(queue)
