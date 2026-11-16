"""Serve the accelerated Suzuka fixture and the built timing display on loopback."""

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import lru_cache
from math import cos, floor, sin
from pathlib import Path
from threading import Event, Thread
from time import monotonic, time_ns
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from openai_codex import CodexError
from pydantic import BaseModel

import f125_core
from demo_strategy import Plan, demo_conditions
from game_mfd import RacePitSync
from gp_advisor import AdvisorView, GpAdvisor, context_key, gp_key
from live_timing import ExitTrends, PlanDisplay, connection_state, live_frame, recommend_plan
from pit_review import Sample, comparison, save_samples
from practice_saves import PracticeSaves
from race import COLORS, DURATION, SCENES, TYRES, WEB_GRID, lap_time, snapshot
from recordings import (
    analysis_view,
    catalog,
    catalog_stops,
    playback,
    recording_analysis,
)
from wheel_input import WheelInput
from voice_control import Microphone


@asynccontextmanager
async def lifespan(app):
    host = os.getenv("F125_UDP_HOST", "127.0.0.1")
    port = int(os.getenv("F125_UDP_PORT", "20777"))
    app.state.pit_ms = int(os.getenv("F125_PIT_LOSS_MS", "20000"))
    if not 0 < app.state.pit_ms <= 120000:
        raise ValueError("F125_PIT_LOSS_MS must be in 1..120000")
    app.state.udp_address = f"{host}:{port}"
    app.state.udp_error = ""
    app.state.record_dir = Path(os.getenv("F125_RECORDING_DIR", Path(__file__).resolve().parent / "data" / "recordings"))
    app.state.advisor = GpAdvisor(app.state.record_dir)
    app.state.game_sync = RacePitSync(native_snapshot)
    try:
        app.state.udp = f125_core.UdpReceiver(host, port, app.state.record_dir, app.state.pit_ms)
        app.state.udp_address = f"{host}:{app.state.udp.port}"
    except OSError as exc:
        app.state.udp = None
        app.state.udp_error = str(exc)
    app.state.handoff = None
    app.state.handoff_analysis = None
    handoff = os.getenv("F125_HANDOFF_RECORDING")
    if handoff and app.state.udp is not None and Path(handoff).name == handoff:
        reader = f125_core.Replay.for_handoff(app.state.record_dir / handoff)
        app.state.handoff = {**reader.advance(reader.duration_ms), "recordingStartMs": int(handoff.split("-")[0])//1000}
        app.state.handoff_analysis = analysis_view(reader.analysis())
    app.state.microphone = Microphone(int(os.getenv("F125_HTTP_PORT","8765")), app.state.record_dir)
    wheel = WheelInput()
    subscribers: set[asyncio.Queue[str]] = set()
    app.state.wheel = wheel
    app.state.subscribers = subscribers
    live_subscribers: set[asyncio.Queue[str]] = set()
    app.state.live_subscribers = live_subscribers

    async def poll():
        while True:
            for key in wheel.poll():
                for queue in subscribers | live_subscribers:
                    if not queue.full():
                        queue.put_nowait(key)
            if app.state.udp is not None:
                for number in app.state.udp.drain_udp_actions():
                    if number == 3 and app.state.microphone.press():
                        continue
                    for queue in live_subscribers:
                        if not queue.full():
                            queue.put_nowait(f"udp/{number}")
            await asyncio.sleep(.016)

    task = asyncio.create_task(poll())
    practice_saves = PracticeSaves(app.state.record_dir, os.getenv("F125_PRACTICE_SAVE_DIR"))
    app.state.practice_saves = practice_saves
    stop_saves = Event()
    save_worker = Thread(target=practice_saves.run, args=(app.state.udp, stop_saves),
                         name="fp-save-recorder", daemon=True)
    save_worker.start()
    try:
        yield
    finally:
        stop_saves.set()
        await asyncio.to_thread(save_worker.join)
        if app.state.game_sync.task:
            app.state.game_sync.task.cancel()
            await asyncio.gather(app.state.game_sync.task,return_exceptions=True)
        if app.state.udp is not None:
            app.state.udp.close()
        await asyncio.to_thread(app.state.microphone.disable)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="F1 25 Race Engineer", lifespan=lifespan)
BUILD = Path(__file__).parent / "web" / "dist"
SESSION_START = monotonic()
PREVIEW_OFFSET = 44
GRID_SECONDS = 18
DNF_SECONDS = 10
LAPS = len(SCENES) - 1
# The sample retires ALO after his pit stop and subsequent return to racing.
DEMO_RETIREMENT_AT = (LAPS - 1) * DURATION + 13


def demo_elapsed():
    return monotonic() - SESSION_START + GRID_SECONDS + PREVIEW_OFFSET


def demo_phase(elapsed):
    race_seconds = LAPS * DURATION
    session, offset = divmod(elapsed, GRID_SECONDS + race_seconds + DNF_SECONDS)
    if offset < GRID_SECONDS:
        return int(session), "grid", 0
    if offset < GRID_SECONDS + race_seconds:
        return int(session), "race", offset - GRID_SECONDS
    return int(session), "dnf", race_seconds - .001


@dataclass(frozen=True)
class DriverRuling:
    driver: str
    kind: str
    reason: str
    seconds: int = 0


@dataclass(frozen=True)
class PenaltyServed:
    driver: str
    kind: str
    seconds: int = 0


RULING_LABELS = {
    "black_white": "흑백기 경고", "time": "시간 페널티",
    "drive_through": "드라이브스루", "stop_go": "스톱 앤 고",
}

# One group per simulated lap, starting with the demo history on L10.
CUES = (
    (("NOR", "선두 진입", "P2 → P1 · 첫 선두 교체"), ("SAI", "피트 진입", "미디엄 사용 9랩 · 피트인"), ("SAI", "트랙 복귀", "하드로 교체 · P16 복귀")),
    (("", "옐로 플래그", "S2 황색기 · 추월 제한"), ("ALB", "피트 진입", "소프트 사용 10랩 · 피트인"), ("", "그린 플래그", "S2 황색기 해제")),
    (("VER", "선두 진입", "NOR 추월 · P2 → P1"), ("ALB", "트랙 복귀", "미디엄으로 교체 · P18 복귀"), ("HAM", "개인 최고 랩", "1:34.108 · 0.216초 단축")),
    (("VER", "선두 유지", ""), ("OCO", "추월 성공", "BEA 추월 · P15 → P14"), ("RUS", "개인 최고 랩", "1:33.714 · 0.108초 단축")),
    (("VER", "선두 유지", ""), ("GAS", "9위 진입", "SAI 추월 · P10 → P9"), ("PIA", "개인 최고 랩", "1:33.422 · 0.153초 단축")),
    (("LEC", "5위 진입", "HAM 추월 · P6 → P5"), DriverRuling("HUL", "drive_through", "피트 출구 적색등 위반"), ("ANT", "개인 최고 랩", "1:34.284 · 0.192초 단축")),
    (("HAM", "6위 진입", "ALO 추월 · P7 → P6"), ("ALO", "7위 진입", "GAS 추월 · P8 → P7"), ("GAS", "개인 최고 랩", "1:33.986 · 0.087초 단축")),
    (PenaltyServed("HUL", "drive_through"), ("YOU", "8위 진입", "GAS 추월 · P9 → P8"), DriverRuling("YOU", "time", "충돌 유발", seconds=5)),
    (("YOU", "개인 최고 랩"), ("GAS", "추격 시작"), DriverRuling("YOU", "black_white", "트랙 리밋 반복 위반")),
    (DriverRuling("GAS", "black_white", "트랙 리밋 반복 위반"), ("YOU", "앞차 추격"), ("VER", "선두 유지")),
    (("ALO", "피트 진입"), ("YOU", "7위 진입"), ("ALO", "타이어 교체")),
    (("", "세이프티카"), ("ALO", "하드 장착"), DriverRuling("GAS", "time", "충돌 유발", seconds=5)),
    (("", "VSC 발령"), DriverRuling("YOU", "time", "트랙 리밋 추가 위반", seconds=3), DriverRuling("KIM", "stop_go", "세이프티카 규정 위반", seconds=10)),
    (("", "그린 플래그"), PenaltyServed("YOU", "time", 5), PenaltyServed("GAS", "time", 5),
     ("ALO", "주행 재개"), PenaltyServed("YOU", "time", 3), PenaltyServed("KIM", "stop_go", 10)),
)


@lru_cache(maxsize=32)
def event_detail(lap, seconds, driver, label):
    if not driver:
        return {"세이프티카": "SC 투입 · 대열 주행", "VSC 발령": "VSC 시작 · 감속 주행",
                "그린 플래그": "VSC 종료 · 정상 주행 재개"}[label]
    cars = snapshot(lap - 17, seconds, drivers=WEB_GRID).cars
    index = next(i for i, car in enumerate(cars) if car.code == driver)
    car = cars[index]
    if label == "피트 진입":
        return f"P{index + 1} · {TYRES[car.tyre]} {car.age}랩 사용"
    if label == "하드 장착":
        return f"{TYRES[car.tyre]} · 새 스틴트 {car.age}랩"
    if label == "타이어 교체":
        return "소프트 탈거 · 하드로 교체"
    if label == "개인 최고 랩":
        return f"{lap_time(car.last)} · P{index + 1}"
    if index:
        ahead = cars[index - 1]
        return f"P{index + 1} · 앞차 {ahead.code}까지 {car.gap - ahead.gap:.3f}초"
    return f"P1 · 2위와 {cars[1].gap - car.gap:.3f}초"


# Seconds within the repeating presentation fixture. Empty sectors mean the whole track.
FLAG_CHANGES = (
    (6, "YELLOW", (2,), "옐로 플래그", "S2 황색기 · 추월 제한"),
    (14, "TRACK CLEAR", (), "그린 플래그", "S2 황색기 해제"),
    (32, "YELLOW", (), "옐로 플래그", "전 구간 황색기"),
    (38, "RED", (), "레드 플래그", "전 구간 적색기"),
    (46, "TRACK CLEAR", (), "그린 플래그", "적색기 해제 · 주행 재개"),
)


def track_flags(offset, scene):
    if scene in (4, 5):
        return ("SC" if scene == 4 else "VSC"), ()
    for at, flag, sectors, _, _ in reversed(FLAG_CHANGES):
        if offset >= at:
            return flag, sectors
    return "TRACK CLEAR", ()


def race_control_snapshot(elapsed):
    cycle, offset = divmod(int(elapsed), LAPS * DURATION)
    events = []
    pending: dict[str, list[DriverRuling]] = {}
    leader = None
    for lap, cues in enumerate(CUES, start=10):
        for cue, entry in enumerate(cues):
            timestamp = (lap - 18) * DURATION + cue * DURATION // len(cues)
            if timestamp > offset:
                return events[::-1], pending
            identity = {"id": f"{cycle}:{timestamp}", "lap": lap}
            if isinstance(entry, PenaltyServed):
                # Identical rulings are served oldest first, one at a time.
                penalties = pending[entry.driver]
                served = next(p for p in penalties if (p.kind, p.seconds) == (entry.kind, entry.seconds))
                penalties.remove(served)
                detail = RULING_LABELS[entry.kind]
                if entry.seconds:
                    detail += f" {entry.seconds}초"
                events.append({**identity, "driver": entry.driver, "label": "페널티 이행", "detail": detail})
                continue
            if isinstance(entry, DriverRuling):
                if entry.kind != "black_white":
                    pending.setdefault(entry.driver, []).append(entry)
                events.append({**identity, "driver": entry.driver, "label": RULING_LABELS[entry.kind],
                               "detail": entry.reason, "ruling": entry.kind, "seconds": entry.seconds})
                continue
            driver, label, *history_detail = entry
            if label in ("랩 완료", "속도 유지", "대열 유지"):
                continue
            if label in ("선두 진입", "선두 유지"):
                if driver == leader:
                    continue
                leader = driver
            events.append({**identity, "driver": driver, "label": label,
                           "detail": history_detail[0] if history_detail else
                           event_detail(lap, timestamp % DURATION, driver, label)})
    return events[::-1], pending


@lru_cache(maxsize=7)
def lap_records(scene):
    """Build consistent lap, sector and personal-best values for the sample once per lap."""
    records = {}
    for lap_index in range(scene + 1):
        frame = snapshot(lap_index, 0, drivers=WEB_GRID)
        for car in frame.cars:
            slot = WEB_GRID.index(car.code)
            last = round(car.last * 1000)
            s1 = round(last * .335 + 480 * sin(slot + lap_index))
            s2 = round(last * .423 + 630 * cos(slot * .8 + lap_index))
            sectors = [s1, s2, last - s1 - s2]
            prior = records.get(car.code)
            best = min(last, prior["bestMs"]) if prior else last
            personal = [min(a, b) for a, b in zip(sectors, prior["personal"])] if prior else sectors
            records[car.code] = {"lastMs": last, "bestMs": best, "sectors": sectors, "personal": personal}
    return records


MINIS_PER_SECTOR = 8
MINIS_PER_LAP = 3 * MINIS_PER_SECTOR


@lru_cache(maxsize=12)
def mini_samples(lap):
    """Split each mock sector into eight timed segments, preserving its exact total."""
    records = lap_records(min(LAPS, max(0, lap - 16)))
    field = []
    for slot, code in enumerate(WEB_GRID):
        splits = []
        for sector, total in enumerate(records[code]["sectors"]):
            weights = [1 + .20 * sin(i + sector) + .035 * cos(lap + i * .7 + slot)
                       for i in range(MINIS_PER_SECTOR)]
            scale = total / sum(weights)
            values = [round(weight * scale) for weight in weights]
            values[-1] += total - sum(values)
            splits.extend(values)
        field.append(splits)
    return field


@lru_cache(maxsize=12)
def mini_colours(lap):
    # Seed the demo with three preceding laps. Compare only to completed laps.
    history = [mini_samples(previous) for previous in range(14, lap)]
    personal = [[min(times) for times in zip(*(field[slot] for field in history))]
                for slot in range(len(WEB_GRID))]
    best = [min(times) for times in zip(*personal)]
    return [[("fastest" if ms < best[i] else "personal" if ms < personal[slot][i] else "normal")
             for i, ms in enumerate(samples)] for slot, samples in enumerate(mini_samples(lap))]


def live_splits(slot, elapsed, car, grid):
    if grid:
        return [], [None]*3
    # Use the same unwrapped distance as the map. Each car clears its own strip at the line.
    distance = .48 + elapsed / DURATION - car.gap / 94
    lap = 18 + floor(distance)
    count = int(car.phase * MINIS_PER_LAP)
    if count == 0:
        # Keep the finished lap visible until the first new split arrives.
        lap -= 1
        count = MINIS_PER_LAP
    samples = mini_samples(lap)[slot]
    sector_times = [sum(samples[i:i+MINIS_PER_SECTOR]) if count >= i+MINIS_PER_SECTOR else None
                    for i in range(0, MINIS_PER_LAP, MINIS_PER_SECTOR)]
    return mini_colours(lap)[slot][:count], sector_times


@lru_cache(maxsize=8)
def completed_laps(scene):
    """Only laps that have crossed the line. The opening frame includes L17."""
    history = []
    if scene:
        # Two historical racing laps seeded before the first frame of this replay.
        # These are part of its initial history, available from the first racing frame.
        for n in (15, 16):
            records = {code: {"lastMs": round((92.9 + slot * .12) * 1000
                                               + 160 * sin(n + slot) + 60 * (n - 15))}
                       for slot, code in enumerate(WEB_GRID)}
            history.append((n, "Clean", records))
    for index in range(1, scene + 1):
        lap = 16 + index
        start = (index - 2) * DURATION
        flags = {track_flags(t, index - 1)[0] for t in range(start, start + DURATION)}
        dry = all(demo_conditions(t)["surface"] == "Dry" for t in range(start, start + DURATION))
        state = next((f for f in ("RED", "SC", "VSC", "YELLOW") if f in flags), "Clean" if dry else "Wet")
        history.append((lap, state, lap_records(index)))
    return history


def build_forecast(entries, history, lap, weather, flag, scheduled, pit_loss_ms=12100):
    active = [c for c in entries.values() if not c["retired"]]
    if entries["YOU"]["retired"] or lap >= 27:
        return None
    field = []
    for c in active:
        code = c["code"]
        mounted = max(1, lap) - c["age"]
        samples = [(n-mounted, record[code]["lastMs"]) for n, state, record in history
                   if n >= mounted and state == "Clean" and not (code == "ALO" and n == 20)]
        field.append((code, c["gapMs"], c["tyre"], c["age"], lap_records(0)[code]["lastMs"], samples))
    player = next(i for i, c in enumerate(active) if c["code"] == "YOU")
    surface = {"Dry": 0, "Damp": 1, "Standing water": 2}[weather["surface"]]
    # Demo uses a five-second nose change. The live feed uses calibrated service losses.
    current_loss = round(pit_loss_ms * .6) if flag in ("SC","VSC") else pit_loss_ms
    result = f125_core.race_forecast(field, player, (max(1, lap), 27),
                                     (surface, not surface and weather["rain"] == "Light rain", flag in ("SC", "VSC")),
                                     pit_loss_ms, scheduled if lap else [],
                                     quick_losses=[[(ms,0),(ms+5000,0)] for ms in (current_loss,pit_loss_ms)])
    for plan in result["plans"]:
        at, tyre = plan["stop"]
        plan["stop"] = {"lap": at, "tyre": tyre}
    result["recommended"] = recommend_plan(result["plans"], entries["YOU"]["position"])
    result["cleanSamples"] = len(field[player][-1])
    return result


def timing_snapshot(elapsed, mode="race", start_tyre="M", scheduled=()):
    scene = 0 if mode == "grid" else 1 + int(elapsed / DURATION) % LAPS
    frame = snapshot(scene, 0 if not scene else elapsed % DURATION, start_tyre, drivers=WEB_GRID)
    by_code = {car.code: car for car in frame.cars}
    grid = [by_code[code] for code in WEB_GRID]
    ranking = f125_core.timing_order([round(car.gap * 1000) for car in grid])
    entries = {}
    events, pending = race_control_snapshot(elapsed)
    cycle, offset = divmod(int(elapsed), LAPS * DURATION)
    alo_retired = offset >= DEMO_RETIREMENT_AT
    if alo_retired:
        events.append({"id": f"{cycle}:{DEMO_RETIREMENT_AT}:retired", "lap": frame.lap,
                       "driver": "ALO", "label": "리타이어", "detail": "모의 레이스 · 주행 종료"})
    flag, yellow_sectors = track_flags(offset, scene)
    for at, _, _, label, detail in FLAG_CHANGES:
        if offset >= at:
            events.append({"id": f"{cycle}:{at}:flag", "lap": 18 + at // DURATION,
                           "driver": "", "label": label, "detail": detail})
    events.sort(key=lambda event: int(event["id"].split(":")[1]), reverse=True)
    if not scene:
        events, pending, flag, yellow_sectors = [], {}, "GRID", ()
    records = lap_records(scene)
    for position, (slot, interval_ms) in enumerate(ranking, 1):
        car = grid[slot]
        retired = (scene > 0 and alo_retired and car.code == "ALO") or (mode == "dnf" and car.code == "YOU")
        if retired and car.code == "ALO":
            stopped = snapshot(scene, DEMO_RETIREMENT_AT % DURATION, drivers=WEB_GRID)
            car = next(c for c in stopped.cars if c.code == car.code)
        speed = 218 + 60 * cos(car.phase * 12.57) + 37 * sin(car.phase * 31.42)
        if frame.caution:
            speed *= .53 if scene == 4 else .68
        pit = car.code == "ALO" and scene == 3 and elapsed % DURATION < 13
        minis, live_sectors = live_splits(slot, DEMO_RETIREMENT_AT if retired and car.code == "ALO"
                                          else elapsed % (LAPS * DURATION), car, scene == 0)
        entries[car.code] = {
            "code": car.code, "color": COLORS[car.code], "position": position,
            "change": slot + 1 - position, "gapMs": round(car.gap * 1000),
            "intervalMs": interval_ms, "tyre": car.tyre, "age": car.age,
            "stints": [{"tyre": tyre, "laps": laps} for tyre, laps in car.stints],
            "minis": minis, "liveSectors": live_sectors,
            "phase": car.phase, "speed": 0 if retired or not scene else 80 if pit else round(speed), "pit": pit, "retired": retired,
            "pendingPenalties": [{"kind": p.kind, "seconds": p.seconds} for p in pending.get(car.code, [])],
            **(records[car.code] if scene else {"lastMs": 0, "bestMs": 0, "personal": [0]*3, "sectors": [0]*3}),
        }
    history = completed_laps(scene)
    weather = demo_conditions(offset if scene else 0)
    forecast = build_forecast(entries, history, frame.lap, weather, flag, scheduled)
    return {
        "forecast": forecast, "paceHistory": [(n, r["YOU"]["lastMs"], state) for n, state, r in history[-5:]],
        "serviceTimes": [[(3000, 0), (8000, 0)]] * 2,
        "session": cycle, "mode": mode, "weather": weather,
        "analysis": demo_analysis(scene, flag, ranking, entries),
        "lap": frame.lap, "scene": SCENES[scene], "flag": flag, "yellowSectors": list(yellow_sectors),
        # Illustrative marshal posts for the demo. The live feed supplies the game's posts.
        "marshalZones": [(start, 3 if flag == "YELLOW" and (not yellow_sectors or start == .44) else 0)
                         for start in (0, .12, .25, .37, .44, .49, .62, .78, .91)],
        "events": events, "player": WEB_GRID.index("YOU"),
        "cars": [entries[name] for name in WEB_GRID],
    }


def demo_analysis(scene, flag, ranking, entries):
    """Use the latest completed fixture lap. Only the opening pair of scenes has
    a clean sample since the last pit, neutralisation or opponent change."""
    waiting = {"chase": None, "defend": None}
    if scene not in (1, 2) or flag != "TRACK CLEAR" or entries["YOU"]["retired"]:
        return waiting
    ordered = [entries[WEB_GRID[slot]] for slot, _ in ranking]
    me = entries["YOU"]
    index = me["position"] - 1

    def pace(leader, follower):
        if any(c["pit"] or c["retired"] for c in (leader, follower)):
            return None
        result = f125_core.closing_pace(follower["intervalMs"], leader["lastMs"], follower["lastMs"])
        if result is None:
            return None
        return {"deltaMs": result[0], "laps": result[1], "lap": 16 + scene,
                "leader": leader["code"], "follower": follower["code"]}

    active = [c for c in ordered if not c["retired"]]
    if any(c["lastMs"] <= 0 or c["pit"] for c in active):
        return waiting
    return {"chase": pace(ordered[index-1], me) if index else None,
            "defend": pace(me, ordered[index+1]) if index+1 < len(ordered) else None}


class AdvisorSettings(BaseModel):
    model: str | None
    effort: str | None


@app.get("/api/settings/codex")
async def codex_settings():
    advisor = app.state.advisor
    model, effort = advisor.preferences()
    try:
        models = await advisor.models()
    except (CodexError, OSError, RuntimeError, TimeoutError) as exc:
        raise HTTPException(503, "Codex 모델 목록을 불러올 수 없음") from exc
    return {"model": model, "effort": effort, "models": models}


@app.put("/api/settings/codex")
async def save_codex_settings(settings: AdvisorSettings):
    try:
        await app.state.advisor.configure(settings.model, settings.effort)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (CodexError, OSError, RuntimeError, TimeoutError) as exc:
        raise HTTPException(503, "Codex 모델 목록을 확인할 수 없음") from exc
    return settings


@app.get("/api/settings/microphone")
def microphone_settings():
    return app.state.microphone.state()


@app.put("/api/settings/microphone")
async def set_microphone(enabled: Annotated[bool, Body(embed=True)]):
    mic = app.state.microphone
    try:
        if enabled:
            mic.enable()
        else:
            await asyncio.to_thread(mic.disable)
    except (ValueError, OSError) as exc:
        raise HTTPException(503, str(exc)) from exc
    return mic.state()


@app.get("/api/health")
def health():
    return {"source": "live", "native_core": f125_core.__name__, "version": f125_core.__version__, "udp": udp_info(native_snapshot())}


def native_snapshot():
    if app.state.udp is None:
        return {"error":app.state.udp_error, "accepted":0, "rejected":0, "ageMs":None, "format":0}
    raw = app.state.udp.snapshot()
    held = app.state.handoff
    if held is not None:
        if raw.get("cars") or (raw.get("uid") and raw["uid"] != "0" and raw["uid"] != held["uid"]):
            app.state.handoff = None
            app.state.handoff_analysis = None
        else:
            return {**held, **{k: raw.get(k) for k in ("accepted", "rejected", "ageMs", "recordDropped", "recordError")}, "handoff": True}
    return raw


def udp_info(raw):
    return {"address":app.state.udp_address, "status":connection_state(raw),
            **{k:raw.get(k) for k in ("ageMs","format","accepted","rejected","error","recordDropped","recordError")}}


@app.get("/api/recordings")
def recordings():
    return catalog(app.state.record_dir)


def review_directory(recording: str):
    if not re.fullmatch(r"\d+-[0-9a-f]{16}", recording):
        raise HTTPException(404, "Unknown recording")
    path = app.state.record_dir / recording
    if not path.is_dir():
        raise HTTPException(404, "Unknown recording")
    return path


@app.post("/api/recordings/{recording}/displayed-exits", status_code=204)
def capture_displayed_exits(recording: str, samples: Annotated[list[Sample], Body(max_length=128)]):
    save_samples(review_directory(recording), samples)


@app.get("/api/recordings/{recording}/pit-review")
def pit_review(recording: str):
    directory = review_directory(recording)
    try:
        data = json.loads((directory / "manifest.json").read_bytes())
        return comparison(directory, catalog_stops(directory, data), data["durationMs"])
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise HTTPException(503, "Recording unavailable") from exc


@app.get("/api/practice-saves")
def practice_save_report():
    return app.state.practice_saves.report()


@app.get("/api/analysis/{recording}")
def analysis(recording: str):
    if recording == "live":
        if app.state.udp is None:
            raise HTTPException(503, "UDP unavailable")
        if app.state.handoff_analysis is not None and native_snapshot().get("handoff"):
            return {**app.state.handoff_analysis, "held":True}
        return analysis_view(app.state.udp.analysis())
    if not any(r["id"] == recording for r in catalog(app.state.record_dir)):
        raise HTTPException(404, "Recording unavailable")
    directory = app.state.record_dir / recording
    return recording_analysis(directory,(directory/"manifest.json").stat().st_mtime_ns)


@app.websocket("/ws/replay/{recording}")
async def replay(socket: WebSocket, recording: str):
    await playback(socket, app.state.record_dir, recording, app.state.subscribers, app.state.wheel,app.state.advisor)


async def live_radio(cmd, raw, frame):
    mic = app.state.microphone
    key = cmd.get("key")
    if not key or key != mic.turn_key:
        raise ValueError("Inactive microphone")
    if (not frame or frame["player"] < 0 or raw.get("handoff") or connection_state(raw) != "Live"
            or cmd.get("session") != frame["session"] or frame["session"] != f'{raw["uid"]}/{raw["epoch"]}'):
        return {"speech":"Waiting for live telemetry."}
    question = cmd.get("question")
    if not isinstance(question,str) or not 0 < len(question.strip()) <= 1500:
        raise ValueError("Invalid radio question")
    service = app.state.advisor
    def validate(choices):
        latest = native_snapshot()
        if mic.turn_key != key or latest.get("handoff") or connection_state(latest) != "Live":
            raise ValueError("Radio context expired")
        picks = [(choices[k]["lap"],choices[k]["tyre"]) if choices[k]["lap"] else None for k in "ABC"]
        updated = live_frame(latest, pit_ms=app.state.pit_ms, proposal=picks)
        if not updated or updated["player"] < 0 or not updated["canPlan"] or context_key(updated) != context_key(frame):
            raise ValueError("Race context expired")
        rows = (updated.get("forecast") or {}).get("plans", [])
        if {p["id"] for p in rows} != set("ABC"):
            raise ValueError("No current forecast")
        for row in rows:
            pick = choices[row["id"]]
            first = next(iter(row["stops"]), None)
            if first != ({"lap":pick["lap"],"tyre":pick["tyre"]} if pick["lap"] else None):
                raise ValueError("Rust forecast changed the requested schedule")
    return await asyncio.wait_for(service.propose(gp_key(raw,False), frame, time_ns()//1_000_000,
        radio={"driverQuestion":question, "frontWingDamagePercentLeftRight":cmd.get("wingDamage")},
        validate_radio=validate), timeout=90)


@app.websocket("/ws/live")
async def live(socket: WebSocket):
    origin = socket.headers.get("origin")
    if origin and origin.split("://", 1)[-1] != socket.headers.get("host"):
        await socket.close(code=1008)
        return
    await socket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue(64)
    app.state.live_subscribers.add(queue)
    plan = None
    session = None
    notice = ""
    last_predictions = None
    displayed = PlanDisplay()
    advisor = AdvisorView(app.state.advisor)
    selected_label = None
    try:
        while True:
            raw = native_snapshot()
            status = connection_state(raw)
            held = bool(raw.get("handoff"))
            identity = (raw.get("uid"), raw.get("epoch"), held)
            if advisor.replay != held:
                advisor.reset()
                advisor = AdvisorView(app.state.advisor, replay=held)
            if identity != session:
                plan, notice, session, selected_label = None, "", identity, None
            await advisor.prepare(raw,app.state.record_dir,raw.get("recordingStartMs",time_ns()//1_000_000))
            frame = advisor.render(raw, pit_ms=app.state.pit_ms)
            keys = [queue.get_nowait() for _ in range(queue.qsize())]
            if frame:
                player = frame["player"]
                driver = frame["cars"][player] if player >= 0 else {}
                if not held and raw.get("recordingId"):
                    frame["recordingId"] = raw["recordingId"]
                    frame["raceFinished"] = any(c["slot"] == raw["player"] and c["result"] in (3,4,5,6,7)
                                                for c in raw.get("cars", ()))
                    if (status == "Live" and driver and frame["isRace"] and frame["mode"] == "race"
                            and not driver.get("pit") and not raw.get("spectating")):
                        frame["displayStamp"] = {"at":raw["timingMs"],"branch":raw["timingBranch"],"tick":raw["timingFrame"]}
                prediction_key = (identity,raw["player"],raw["spectating"],frame["mode"],frame["isRace"],
                                  driver.get("tyre"),driver.get("pit"))
                if status == "Live":
                    last_predictions = (prediction_key, frame["lap"], frame["forecast"], frame["boxNowPosition"], frame["serviceForecast"])
                elif not frame["forecast"] and last_predictions and last_predictions[0] == prediction_key:
                    _, frame["predictionLap"], frame["forecast"], frame["boxNowPosition"], frame["serviceForecast"] = last_predictions
                tyre = frame["cars"][player]["tyre"] if player >= 0 else None
                if plan is None and tyre:
                    car = next(c for c in raw["cars"] if c["slot"]==raw["player"])
                    restored, selected_label = app.state.advisor.restore_decision(gp_key(raw,held),frame["session"],frame["lap"],car["currentMs"])
                    plan = restored or Plan(start=tyre, stops=())
                token = ("held/" if held else "") + f'{frame["session"]}:{frame["mode"]}:{frame["lap"]}'
                frame["microphoneMode"] = app.state.microphone.state()["enabled"]
                frame.update(token=token, selectedPlan=selected_label, plan=plan.wire() if plan else {"start":None,"stops":[]},
                             notice=notice,wheel={"keys":keys,"device":app.state.wheel.description(),"bindings":{}})
                frame["gameSync"] = app.state.game_sync.observe(raw)
            else:
                last_predictions = None
            displayed.update(frame, raw)
            await socket.send_json({"status":status,"udp":udp_info(raw),"frame":frame,"wheelKeys":keys})
            try:
                cmd = json.loads(await asyncio.wait_for(socket.receive_text(),timeout=.1))
                latest = native_snapshot()
                if isinstance(cmd,dict) and cmd.get("type") == "radio":
                    try:
                        turn = await live_radio(cmd, latest, frame)
                    except (CodexError, OSError, RuntimeError, ValueError, TypeError, TimeoutError) as exc:
                        turn = {"error": type(exc).__name__, "speech":"Radio link unavailable. Try again."}
                    await socket.send_json({"radio":turn})
                    continue
                if isinstance(cmd,dict) and cmd.get("type") in ("askCodex","applyCodex"):
                    if cmd["type"] == "askCodex" and app.state.microphone.state()["enabled"]:
                        raise ValueError("Microphone mode · UDP 3")
                    current = advisor.render(latest, pit_ms=app.state.pit_ms)
                    if not current or bool(latest.get("handoff")) != held or connection_state(latest) == "UDP error":
                        raise ValueError("실시간 수신 대기")
                    current["token"] = ("held/" if held else "") + f'{current["session"]}:{current["mode"]}:{current["lap"]}'
                    plan = advisor.command(cmd,latest,current,plan,time_ns()//1_000_000)
                    notice = advisor.message
                    if cmd["type"] == "applyCodex" and plan is not None and not held:
                        app.state.game_sync.submit(latest,current,plan)
                    continue
                current = advisor.render(latest, pit_ms=app.state.pit_ms)
                if (not isinstance(cmd,dict) or cmd.get("type") != "confirm" or not frame or not current
                        or not plan or bool(latest.get("handoff")) != held or connection_state(latest)=="UDP error" or not current["canPlan"]
                        or cmd.get("token")!=frame["token"] or any(current[k]!=frame[k] for k in ("session","lap","mode"))):
                    raise ValueError("세션 또는 랩 변경 · 현재 상태에서 다시 선택")
                if cmd.get("planId") in ("A","B","C") and current["mode"] == "race":
                    row = next((p for p in (current.get("forecast") or {}).get("plans", []) if p["id"] == cmd["planId"]), None)
                    if not row or row.get("codexExpired") or (row.get("codexReason") and row["stops"] != cmd.get("stops")):
                        raise ValueError("플랜이 변경됨 · 현재 플랜을 다시 선택해")
                candidate = plan.confirm(cmd,0 if current["mode"]=="grid" else current["lap"],current["totalLaps"],
                                         replace_future=cmd.get("replaceFuture") is True,
                                         allow_no_stop=any(p.get("stops")==[] for p in (current.get("forecast") or {}).get("plans",[])) or any(p["start"]==cmd.get("start") and not p["stops"]
                                                           for p in current.get("preRace",{}).get("plans",())))
                stock = current["availableTyres"]
                if stock is not None and any(s["tyre"] not in stock for s in cmd["stops"]):
                    raise ValueError("가용 타이어 세트 변경 · 다시 선택")
                car = next(c for c in latest["cars"] if c["slot"]==latest["player"])
                selected_label = cmd.get("planId") if cmd.get("planId") in ("A","B","C") else None
                proposal_id = cmd.get("proposalId") if cmd.get("proposalId")==current.get("advisor",{}).get("id") else None
                app.state.advisor.commit(gp_key(latest,held),current["session"],candidate,proposal_id,
                                         decision=(current["lap"],car["currentMs"],selected_label))
                plan = candidate
                if not held:
                    app.state.game_sync.submit(latest,current,plan)
                notice = "녹화 시뮬레이션에 적용됨" if held else "대시보드 전략 적용됨"
            except TimeoutError:
                continue
            except (TypeError,ValueError) as exc:
                notice = str(exc)
    except WebSocketDisconnect:
        return
    finally:
        advisor.reset()
        app.state.live_subscribers.discard(queue)


@app.websocket("/ws/demo")
async def demo(socket: WebSocket):
    origin = socket.headers.get("origin")
    if origin and origin.split("://", 1)[-1] != socket.headers.get("host"):
        await socket.close(code=1008)
        return
    await socket.accept()
    plan = Plan()
    selected_label = None
    session = None
    queue: asyncio.Queue[str] = asyncio.Queue(64)
    app.state.subscribers.add(queue)
    path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "f125manager/PitWall/wheel.json"
    try:
        bindings = json.loads(path.read_text(encoding="utf8")) if path.is_file() else {}
    except (OSError, ValueError):
        bindings = {}
    trends = ExitTrends()
    notice = ""
    try:
        while True:
            current, mode, elapsed = demo_phase(demo_elapsed())
            if session != current:
                plan, notice, selected_label = Plan(), "", None
            session = current
            frame = timing_snapshot(elapsed, mode, plan.start, plan.stops)
            frame["session"] = current
            trends.update(frame, elapsed)
            token = f"{session}:{frame['lap']}:{mode}"
            keys = [queue.get_nowait() for _ in range(queue.qsize())]
            await socket.send_json({**frame, "token": token, "plan": plan.wire(), "selectedPlan": selected_label, "notice": notice,
                                    "wheel": {"keys": keys, "device": app.state.wheel.description(),
                                              "bindings": bindings}})
            try:
                raw = await asyncio.wait_for(socket.receive_text(), timeout=.1)
            except TimeoutError:
                continue
            try:
                cmd = json.loads(raw)
                if not isinstance(cmd, dict) or cmd.get("token") != token:
                    raise ValueError("랩 변경 · 다시 선택")
                now_session, now_mode, now_offset = demo_phase(demo_elapsed())
                if (now_session, now_mode, int(now_offset / DURATION)) != (session, mode, int(elapsed / DURATION)):
                    raise ValueError("랩 변경 · 다시 선택")
                if cmd.get("type") == "confirm" and mode != "dnf":
                    plan = plan.confirm(cmd, frame["lap"])
                    selected_label = cmd.get("planId") if cmd.get("planId") in ("A","B","C") else None
                    notice = "전략 적용됨"
                else:
                    raise ValueError("지금 적용할 수 없음")
            except (ValueError, TypeError) as exc:
                notice = str(exc)
    except WebSocketDisconnect:
        return
    finally:
        app.state.subscribers.discard(queue)


if BUILD.is_dir():
    app.mount("/", StaticFiles(directory=BUILD, html=True), name="dashboard")

