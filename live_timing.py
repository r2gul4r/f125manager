"""Adapt one native UDP snapshot to the dashboard contract. No fixture data is used."""
from collections import Counter
from itertools import pairwise
from statistics import median
from unicodedata import normalize

import f125_core

COMPOUNDS = {16: "S", 17: "M", 18: "H", 7: "I", 8: "W"}
RAIN = ("Clear", "Light cloud", "Overcast", "Light rain", "Heavy rain", "Storm")
SESSION = ("Unknown", "FP1", "FP2", "FP3", "Practice", "Q1", "Q2", "Q3", "Qualifying",
           "One-shot qualifying", "SQ1", "SQ2", "SQ3", "Sprint qualifying", "Sprint qualifying",
           "Race", "Race 2", "Race 3", "Time Trial", "Sprint", "Sprint")
EVENTS = {"FLBK":"플래시백", "FTLP":"최고 랩", "RTMT":"리타이어", "RDFL":"레드 플래그",
          "OVTK":"추월", "SCAR":"세이프티카 상태 변경", "PENA":"페널티", "RCWN":"레이스 우승",
          "LGOT":"레이스 시작", "SEND":"세션 종료", "SSTA":"세션 시작", "COLL":"차량 접촉",
          "DTSV":"드라이브스루 이행", "SGSV":"스톱 앤 고 이행"}

# EA event packet, penaltyType and infringementType appendices (2025/2026).
PENALTIES = (
    "드라이브스루", "스톱 앤 고", "그리드 강등", "페널티 이행 알림", "시간 페널티", "경고", "실격",
    "포메이션 랩 제외", "장시간 정차 경고", "타이어 규정 위반", "현재 랩 무효", "현재·다음 랩 무효",
    "현재 랩 무효", "현재·다음 랩 무효", "현재·이전 랩 무효", "현재·이전 랩 무효", "리타이어", "흑기 경고",
)
INFRINGEMENTS = (
    "저속 주행 방해", "역주행 방해", "출발선 후진", "큰 충돌", "경미한 충돌", "충돌 후 순위 미반환",
    "충돌 후 여러 순위 미반환", "코너 절단으로 시간 이득", "코너 절단 추월", "코너 절단 다중 추월",
    "피트 출구 경계선 침범", "청기 무시", "황기 무시", "드라이브스루 미이행", "드라이브스루 누적",
    "드라이브스루 이행 기한 임박", "이번 랩 드라이브스루 이행", "피트레인 과속", "장시간 정차",
    "타이어 규정 미준수", "페널티 누적", "반복 경고", "실격 임박", "지정 타이어 선택", "지정 타이어 선택",
    "코너 절단", "트랙 이탈", "트랙 이탈로 소폭 시간 이득", "트랙 이탈로 시간 이득", "트랙 이탈로 큰 시간 이득",
    "벽 접촉 주행", "플래시백 사용", "트랙으로 리셋", "피트레인 방해", "부정 출발", "세이프티카 상황 충돌",
    "세이프티카 상황 추월", "세이프티카 속도 위반", "VSC 속도 위반", "포메이션 랩 저속 주행",
    "포메이션 랩 정차", "기계 고장", "차량 파손", "세이프티카 대열 이탈", "흑기 제한 시간",
    "스톱 앤 고 미이행", "드라이브스루 미이행", "엔진 부품 교체", "기어박스 교체", "파르크 페르메 위반",
    "리그 그리드 강등", "재시도", "부당한 시간 이득", "의무 피트스톱", "속성 부여",
)


def race_events(raw, codes, session):
    result = []
    slots = 24 if raw["format"] == 2026 else 22

    def driver(slot):
        return codes.get(slot, f"#{slot + 1}") if 0 <= slot < slots else ""

    log = raw.get("eventLog")
    entries = ((f"{raw['uid']}/{epoch}", event) for epoch, event in log) if log is not None else (
        (session, event) for event in raw["events"])
    for event_session, (frame, kind, slot, lap, *extra) in entries:
        if kind not in EVENTS:
            continue
        data = bytes(extra[0]) if extra else b""
        name = driver(slot) if kind in ("FTLP", "RTMT", "RCWN", "DTSV", "SGSV", "COLL", "OVTK") else ""
        label, detail = EVENTS[kind], ""
        if kind == "PENA" and data:
            penalty, reason, slot, other, seconds, _, _ = data
            name = driver(slot) or "선수 미상"
            label = PENALTIES[penalty] if penalty < len(PENALTIES) else f"페널티 #{penalty}"
            if seconds and penalty in (1, 4):
                label += f" {seconds}초"
            if penalty not in (12, 13, 15):
                detail = INFRINGEMENTS[reason] if reason < len(INFRINGEMENTS) else f"사유 코드 {reason}"
                if reason in (3, 4, 5, 6, 8, 9, 35, 36) and other != slot and driver(other):
                    detail += f" · 상대 {driver(other)}"
        elif kind in ("OVTK", "COLL") and data:
            rival = driver(data[0])
            detail = f"상대 {rival}" if rival else ""
        result.append({"id": f"{event_session}:{frame}:{kind}:{slot}:{data.hex()}", "lap": lap,
                       "driver": name, "label": label, "detail": detail})
    return result


def connection_state(raw):
    if raw.get("handoff"):
        return "Last recording"
    if raw.get("error"):
        return "UDP error"
    age = raw["ageMs"]
    if age is None:
        return "Waiting for UDP" if not raw["accepted"] else "Waiting for timing"
    if raw.get("paused") and raw.get("cars"):
        return "Paused"
    if age > 10000:
        return "UDP disconnected"
    if age > 2000:
        return "Stale data"
    return "Live" if raw.get("cars") else "Waiting for timing"


def driver_codes(rows):
    codes = {}
    for row in rows:
        words = normalize("NFKD",row["name"]).encode("ascii","ignore").decode().strip().split()
        codes[row["slot"]] = words[-1][:3].upper() if words else ""
    counts = Counter(codes.values())
    return {slot: code if code and counts[code] == 1 and not code.startswith("#") else f"#{slot+1}"
            for slot, code in codes.items()}


def car_row(raw, c, code):
    history = c.get("history", [])
    completed = [(n, ms, sectors, valid) for n, (ms, sectors, valid) in enumerate(history, 1)
                 if ms and n < c["lap"]]
    last, last_valid = next(((sectors, valid) for n, _, sectors, valid in reversed(completed)
                             if n == c["lap"]-1), ([0]*3, 0))
    previous = 0
    stints = []
    for end, compound in c.get("stints", []):
        last_lap = max(0, c["lap"]-1) if end == 255 else end
        if last_lap < previous or last_lap >= max(c["lap"], 1):
            break
        stints.append({"tyre": COMPOUNDS.get(compound), "laps": last_lap-previous})
        previous = last_lap
    tyre, age = current_tyre(c)
    if tyre and age is not None and (not stints or stints[-1]["tyre"] != tyre):
        stints.append({"tyre": tyre, "laps": age})
    elif tyre and stints and age is not None:
        stints[-1]["laps"] = age
    distance = c["distance"]
    mini_progress = None
    if raw.get("sectorStarts") and distance is not None:
        bounds = [0, *raw["sectorStarts"], raw["length"]]
        mini_progress = [max(0, min(8, int(8*(distance-a)/(b-a)))) for a,b in pairwise(bounds)]
    penalties, drive_through, stop_go = c.get("penalties", (0,0,0))
    show_finish = (c["lap"] > 1 and 0 <= c.get("currentMs", 5000) < 5000
                   and not c["pit"] and c["result"] == 2 and not any(c["splits"]))
    s3 = last[2] if show_finish else 0
    return {"code": code, "color": "#" + bytes(c.get("rgb", (135,135,135))).hex().upper(),
            "world": c.get("world"), "position": c["position"], "change": c["grid"]-c["position"] if c["grid"] else None,
            "gapMs": c.get("raceGapMs",c["gapMs"]), "intervalMs": c["intervalMs"] if c.get("intervalValid", True) else None, "lastMs": c["lastMs"],
            "bestMs": min((ms for _, ms, _, valid in completed if valid & 1), default=0),
            "sectors": last, "personal": [min((sec[i] for _, _, sec, v in completed
                                               if sec[i] and v & (2 << i)), default=0) for i in range(3)],
            "liveSectors": [*c["splits"],s3], "miniProgress": mini_progress, "minis": c.get("minis", []),
            "miniLastLap": c.get("miniLastLap",False),
            "sectorEligible": [not c.get("invalid"), not c.get("invalid"), bool(last_valid & 8)],
            "pendingPenalties": ([{"kind":"time","seconds":penalties}] if penalties else [])
                + [{"kind":"drive_through","seconds":0}]*min(drive_through,1)
                + [{"kind":"stop_go","seconds":0}]*min(stop_go,1),
            "wheelWear": c.get("wheelWear"), "tyre": tyre, "age": age if tyre else None, "stintAge": age is not None and c.get("age") is None,
            "stints": stints, "speed": c.get("speed"), "pit": c["pit"], "retired": c["result"] in (4,5,6,7),
            "phase": (distance / raw["length"]) % 1 if distance is not None and raw["length"] else None}


def colour_sectors(cars):
    best = [None, None, None]
    for car in cars:
        times = car["liveSectors"]
        for i, ms in enumerate(times):
            for candidate in (car["personal"][i], ms if car["sectorEligible"][i] else 0):
                if candidate and (best[i] is None or candidate < best[i]):
                    best[i] = candidate
    for car in cars:
        eligible = car.pop("sectorEligible")
        car["sectorStatus"] = []
        for i, ms in enumerate(car["liveSectors"]):
            status = "pending"
            if ms and eligible[i]:
                if ms == best[i]:
                    status = "fastest"
                elif not car["personal"][i] or ms <= car["personal"][i]:
                    status = "personal"
                else:
                    status = "normal"
            car["sectorStatus"].append(status)


def battle_gap(leader, follower):
    gap = follower["intervalMs"]
    if not gap or not follower.get("intervalValid", True) or any(c["pit"] or c["result"] != 2 for c in (leader, follower)):
        return None
    fg, lg = (c.get("raceGapMs",c["gapMs"]) for c in (follower,leader))
    if fg is None or lg is None:
        return None
    leader_gap = max(0, fg-lg)
    if abs(gap-leader_gap) > max(2000, leader_gap/5):
        return None
    return gap


def live_pace(leader, follower, trend, raw):
    gap = battle_gap(leader,follower)
    if gap is None:
        return None
    # The player crosses the timing line inside the lane on some circuits.
    # Both the entry and exit lap may include service time.
    def clean_last(car):
        if car["lap"] < 2 or car["lap"]-1 in pit_laps(raw,car):
            return 0
        if car.get("age") in (0, 1) and car.get("stints") and len(car["stints"]) > 1:
            return 0
        history = car.get("history", [])
        if len(history) >= car["lap"]-1 and not history[car["lap"]-2][2] & 1:
            return 0
        return car["lastMs"]
    leading, following = clean_last(leader), clean_last(follower)
    window = None
    partial = False
    if trend and tuple(trend[:2]) == (leader["slot"], follower["slot"]):
        reference = 0
        for car, last in ((follower,following),(leader,leading)):
            reference,partial = running_pace(dict(car,lastMs=last),raw.get("length",0),pit_laps(raw,car),
                                             raw.get("sectorStarts"))
            if reference:
                break
        if not reference:
            timed = [c["lastMs"] for c in raw.get("cars", []) if c["result"] == 2 and c["lap"] > 1
                     and not c["pit"] and (c.get("age") or 0) > 1 and c["lastMs"] > 0]
            reference = int(median(timed)) if timed else 0
        result = f125_core.battle_projection(gap, trend[2], reference)
        window = trend[3]
    elif leader["lap"] == follower["lap"]:
        estimates = [running_pace(c,raw.get("length",0),pit_laps(raw,c),raw.get("sectorStarts"))
                     for c in (leader,follower)]
        partial = all(part for _,part in estimates) and (
            all(c.get("history") for c in (leader,follower)) or
            abs((leader.get("distance") or 0)-(follower.get("distance") or 0)) <= .05*raw.get("length",0))
        result = (f125_core.closing_pace(gap, estimates[0][0], estimates[1][0]) if partial
                  else f125_core.closing_pace(gap, leading, following))
    else:
        return None
    if result is None:
        return None
    return {"deltaMs": result[0], "laps": result[1], "gapMs":gap, "windowMs":window,
            "partialLap":partial, "lap":follower["lap"] if window or partial else leader["lap"]-1,
            "leader": leader["code"], "follower": follower["code"]}


def displayed_battle(leader, follower, average):
    gap = battle_gap(leader,follower)
    if gap is None:
        return None
    known = average and tuple(average[:2]) == (leader["slot"],follower["slot"])
    eta = None
    if gap <= 1000:
        eta = 0
    elif known and average[3] > 0:
        eta = max(1,average[4] or 0)
    return {"leader":leader["code"],"follower":follower["code"],"gapMs":gap,
            "deltaMs":average[3] if known else 0,
            "laps":eta,
            "lap":average[2] if known else follower["lap"], "sampleLaps":average[5] if known else 0}


def running_pace(car, length, pit_laps=(), sector_starts=None):
    """Estimate lap duration from elapsed game time and share of lap completed."""
    previous = car.get("history", [])
    completed = car["lap"] - 1
    reference = car["lastMs"] if completed > 0 else 0
    if completed in pit_laps or (completed > 0 and len(previous) >= completed and not previous[completed-1][2] & 1):
        reference = next((ms for n,(ms, _, valid) in reversed(list(enumerate(previous[:completed],1)))
                          if ms and valid & 1 and n not in pit_laps), 0)
    fraction = (car.get("distance") or 0) / length if length else 0
    elapsed = car.get("currentMs", 0)
    if (car["lap"] not in pit_laps and not car["pit"] and car.get("driverStatus",4) not in (0,2,3)
            and not car.get("invalid") and .04 <= fraction <= 1 and elapsed >= 2500):
        if sector_starts:
            # Project only the unfinished sector by distance. Use this driver's measured
            # split distribution and the current lap's completed sectors for the rest.
            bounds = [0,*sector_starts,length]
            sector = sum(car["distance"] >= start for start in sector_starts)
            slow_laps = car.get("slowLaps", ())
            sectors = [times for n,(ms,times,v) in enumerate(previous[:completed],1)
                       if ms and v & 15 == 15 and all(times) and n not in pit_laps and n not in slow_laps][-3:]
            splits = car.get("splits",[])[:sector]
            if sectors and len(splits)==sector and all(splits) and elapsed >= sum(splits):
                normal = [median(row[i] for row in sectors) for i in range(3)]
                progress = (car["distance"]-bounds[sector])/(bounds[sector+1]-bounds[sector])
                sector_elapsed = elapsed - sum(splits)
                sector_time = sector_elapsed + (1-progress)*normal[sector]
                if len(sectors) >= 2 and car["lap"] not in slow_laps:
                    # Distance progress is biased by braking zones and long straights.
                    # Bound its projection by observed sector times, scaled by this
                    # lap's completed splits. The elapsed clock is always a floor.
                    ratio = sum(splits)/sum(normal[:sector]) if sector else 1
                    observed = [row[sector] for row in sectors]
                    low = min(observed) * min(1, ratio)
                    high = max(observed) * max(1, ratio)
                    sector_time = max(sector_elapsed, min(high, max(low, sector_time)))
                estimate = round(sum(splits) + sector_time + sum(normal[sector+1:]))
                if 30000 <= estimate <= 600000:
                    return estimate, True
        projected = round(elapsed / fraction)
        if 30000 <= projected <= 600000:
            if not reference:
                return projected, True
            # Reduce corner/start-line bias early in the lap.
            weight = fraction / 2
            return round(reference*(1-weight) + projected*weight), True
    return reference, False


def pit_laps(raw, car):
    entries = [end for end, _ in car.get("stints", []) if 0 < end < 255]
    if car["slot"] == raw["player"]:
        entries.extend(p[0] for p in raw.get("pitComparisons", []))
    return {n for entry in entries for n in (entry, entry+1)}


def fitted_set(car):
    return next((s for s in car.get("tyreSets", ()) if s[5] and
                 (car.get("compound") not in COMPOUNDS or s[0] == car["compound"])), None)


def current_tyre(car):
    compound = car.get("compound")
    fitted = fitted_set(car)
    stints = car.get("stints", ())
    current = stints[-1][1] if stints and stints[-1][0] == 255 else None
    if compound not in COMPOUNDS:
        compound = fitted[0] if fitted else current
    age = car.get("age")
    if age is None and compound in COMPOUNDS and current == compound and car.get("tyreDataPublic"):
        age = max(0,car["lap"]-1-max((n for n,_ in stints if n<255),default=0))
    return COMPOUNDS.get(compound), age


def available_sets(car):
    sets = []
    for compound, wear, available, life, delta, fitted in car.get("tyreSets", ()):
        if available and not fitted and life and compound in COMPOUNDS:
            sets.append((COMPOUNDS[compound], delta, life, wear))
    sets.sort(key=lambda s: (-s[2],s[1],s[3]))
    return [(key, delta, life) for key, delta, life, _ in sets]


def annotate_wear(plan, car, rates):
    """Use the same set ordering as the race simulation; wear and life are different units."""
    inventory = sorted((s for s in car.get("tyreSets", ()) if s[2] and not s[5] and s[3]),
                       key=lambda s: (-s[3], s[4], s[1]))
    lap = car["lap"]
    fitted = fitted_set(car)
    sets = [(lap, fitted, True)]
    for stop in plan.get("stops", ()):
        selected = next((s for s in inventory if COMPOUNDS.get(s[0]) == stop["tyre"]), None)
        if selected:
            inventory.remove(selected)
        sets.append((stop["lap"], selected, False))
    result = {}
    for first, last, tyre, reason in plan.get("tyreIssues", ()):
        if reason != "life":
            continue
        start, tyre_set, current = next(s for s in reversed(sets) if s[0] <= first)
        if not tyre_set or COMPOUNDS.get(tyre_set[0]) != tyre:
            continue
        length = last - start + 1
        life = tyre_set[3]
        wear = max(car.get("wheelWear") or [tyre_set[1]]) if current else tyre_set[1]
        rate = rates.get(tyre, {}).get("wearPct")
        result[first] = {"wearPct": min(100, round(wear + length * rate, 1)) if rate else None,
                         "excessPct": round(100 * (length-life) / life, 1) if life else None}
    plan["wearRisk"] = result


def compound_slopes(car, exclude):
    """Within-stint lap differences; never compare laps across a tyre change."""
    history = car.get("history", ())
    trends = {}
    start = 1
    for end, compound in car.get("stints", ()):
        last = min(car["lap"]-1, end, len(history))
        tyre = COMPOUNDS.get(compound)
        for n in range(max(3,start+1),last+1):
            a, b = history[n-2:n]
            if (tyre and n not in exclude and n-1 not in exclude and a[2]&1 and b[2]&1
                    and all(30000 <= row[0] <= 600000 for row in (a,b))):
                trends.setdefault(tyre,[]).append(b[0]-a[0])
        start = end+1
    return [(tyre,round(median(values)),min(len(values),255)) for tyre,values in trends.items()]


def surface_for(weather):
    return 2 if weather in (4,5) else int(weather == 3)


def recommend_plan(plans, position):
    def score(plan):
        ranks = plan["scenarioRanks"]
        gains = sum(rank < position for rank in ranks)
        unavailable = any(reason in ("stock","weather") for _,_,_,reason in plan.get("tyreIssues", ()))
        return (unavailable, -gains, sum(ranks), max(ranks), plan["lifeShortfall"], plan["remainingMs"])

    return min(plans, key=score)["id"]


def forecast(raw, rows, me, surface, stops, pit_ms, proposal=None):
    active = [r for r in rows if r["result"] == 2]
    lap = me["lap"]
    if not 0 < lap < raw["totalLaps"] or me not in active or me["pit"]:
        return None, "In pit lane" if me["pit"] else None
    if raw.get("forecastGaps"):
        gaps = dict(raw["forecastGaps"])
    elif raw["comparableLaps"]:
        gaps = {c["position"]: c.get("raceGapMs", c["gapMs"]) for c in active}
    else:
        return None, "Waiting for timing gaps"
    if any(gaps.get(c["position"]) is None for c in active):
        return None, "Waiting for timing gaps"
    # Flashback restores lap packets before the tyre history and inventory.
    # Wait for both before pricing another stop on a car that already serviced.
    if (not me.get("tyreSets") and not me.get("stints") and not me.get("history")
            and any(e[1] == "FLBK" and e[3] == lap for e in raw.get("events", ()))):
        return None, "Waiting for tyre history"
    if me.get("pitStops") and (not me.get("stints") or not fitted_set(me)):
        return None, "Waiting for tyre history"
    paces = [running_pace(c, raw["length"], pit_laps(raw,c),raw.get("sectorStarts")) for c in active]
    observed = [ms for ms, _ in paces if ms > 0]
    if not observed:
        return None, "Waiting for pace"
    field = []
    fitted_lives = []
    samples_used = 0
    private = []
    observations = []
    for car, (pace, _) in zip(active, paces):
        tyre, age = current_tyre(car)
        if age is None or not tyre:
            if car == me:
                return None, "Waiting for tyre data"
            # Keep this car in the rank calculation using its observed gap and pace.
            # A neutral model baseline is internal; withhold its tyre-specific predictions.
            private.append(car["code"])
            tyre, age = tyre or "M", 0
        reference = pace or int(median(observed))
        # Simulate everyone from the player's lap using the observed leader gaps.
        age_at_start = max(0, age + lap - car["lap"])
        exclude = pit_laps(raw, car) | set(car.get("slowLaps",()))
        start = max(2, car["lap"]-age, 1+max((end for end,_ in car.get("stints",[]) if end < 255), default=0))
        samples = [(age-(car["lap"]-n), ms) for n,(ms,_,valid) in enumerate(car.get("history", []),1)
                   if start <= n < car["lap"] and n not in exclude and valid & 1 and 30000 <= ms <= 600000][-5:]
        field.append((car["code"], gaps[car["position"]], tyre, age_at_start, reference, samples))
        fitted = fitted_set(car)
        if fitted:
            fitted_lives.append((car["code"], fitted[3]))
        if car == me:
            samples_used = len(samples)
        observations.append((car["code"],available_sets(car),car.get("penalties",(0,0,0))[0],
                             car.get("servePenalty",False),car["pit"] or car.get("driverStatus")==2,car.get("accruedPitLossMs"),
                             compound_slopes(car,exclude)))
    stock = available_sets(me)
    used = {COMPOUNDS.get(code) for _, code in me.get("stints", ())} - {None}
    serviced = bool(me.get("pitStops") and (len(used) >= 2 or used & {"I","W"}))
    if me.get("tyreSets") and not stock and not serviced:
        return None, "No available tyre set"
    player_pace = paces[active.index(me)][0] or int(median(observed))
    outlook = {}
    for minutes, weather, _ in sorted(raw.get("weatherOutlook", [])):
        if minutes > 0:
            at = lap + max(1, round((minutes*60000 + me.get("currentMs",0))/player_pace))
            if at <= raw["totalLaps"]:
                outlook[at] = surface_for(weather)
    current_services = raw.get("serviceForecast")
    current_losses = [(ms, n) for _, ms, n in current_services] if current_services else None
    result = f125_core.race_forecast(field, active.index(me), (lap, raw["totalLaps"]),
                                     (surface, False, raw["safety"] in (1,2)), pit_ms, stops,
                                     (sorted(outlook.items()),stock,fitted_lives,None),
                                     (observations,raw["neutralPitLoss"][0] if raw.get("neutralPitLoss") else None),None if isinstance(proposal, list) else proposal,
                                     [current_losses, raw.get("greenServiceLosses")],serviced,proposal if isinstance(proposal,list) else None)
    same_lap={c["code"] for c in active if c["lap"]==lap}
    exits=result.get("tyreExits") or []
    if exits and current_losses and current_losses[0][1]:
        exits[0]["validation"]=raw.get("tyreLossValidation")
    for row in result.get("tyreExits", [])[:4]:
        if "lapPaceMs" in row:
            row["lapPaceMs"]=[(code,ms) for code,ms in row["lapPaceMs"] if code in same_lap]
    for p in result["plans"]:
        p["timeLeftMs"] = max(0, p["remainingMs"] - me.get("currentMs", 0))
        at, tyre = p["stop"]
        p["stop"] = {"lap": at, "tyre": tyre}
        p["stops"] = [{"lap": n, "tyre": t} for n,t in p["stops"]]
    if proposal and not isinstance(proposal,list):
        result["codexPlan"] = result["plans"].pop()
    result["recommended"] = recommend_plan(result["plans"], me["position"])
    result["cleanSamples"] = samples_used
    result["inventoryKnown"] = bool(stock)
    if any(code in private for code in result["cutRivals"]):
        result["cutScenarios"] = {}
    for code in private:
        result["rivals"].pop(code, None)
    result["privateRivals"] = len(private)
    result["partialLap"] = paces[active.index(me)][1]
    return result, None


class ExitTrends:
    """Compare successive forecasts for the same pit lap, neighbour and side."""

    def __init__(self):
        self.key = self.stamp = None
        self.current = {}
        self.previous = {}

    def update(self, frame, stamp):
        key = (frame["session"], frame["player"], frame["mode"])
        if key != self.key or (self.stamp is not None and stamp < self.stamp):
            self.current, self.previous, self.stamp = {}, {}, None
        self.key = key
        if stamp != self.stamp:
            self.previous, self.current = self.current, {}
            self.stamp = stamp
        basis = frame.get("predictionLap", frame["lap"])
        for offset, row in enumerate((frame.get("forecast") or {}).get("tyreExits", ())):
            for side, field in (("ahead", "before"), ("behind", "after")):
                gap = row[side + "GapMs"]
                if gap is None:
                    continue
                target = (basis + offset, side, row[field])
                prior = self.previous.get(target, gap)
                row[side + "Trend"] = "closing" if gap < prior else "opening" if gap > prior else "steady"
                self.current[target] = gap


class PlanDisplay:
    """Keep the last displayed plans separately from actionable forecasts."""

    def __init__(self):
        self.key = None
        self.last = None
        self.in_pit = False
        self.trends = ExitTrends()

    def update(self, frame, raw):
        if (not frame or frame["player"] < 0 or not frame["isRace"] or frame["mode"] != "race"
                or not any(c["slot"] == raw["player"] and c["result"] == 2 for c in raw["cars"])
                or frame["lap"] >= frame["totalLaps"]):
            self.key = self.last = None
            self.in_pit = False
            self.trends = ExitTrends()
            return
        car = frame["cars"][frame["player"]]
        completed = sum(stop["exitMs"] is not None for stop in frame["pitComparisons"])
        key = (frame["session"], raw["player"], frame["trackId"], completed, car["tyre"])
        same_visit = car["pit"] and self.key and self.key[:-1] == key[:-1]
        if (self.key != key and not same_visit) or (self.in_pit and not car["pit"]):
            self.key, self.last = key, None
        self.in_pit = car["pit"]
        if frame["forecast"]:
            self.trends.update(frame, raw.get("accepted", 0))
            self.last = {**frame["forecast"], "lap": frame.get("predictionLap", frame["lap"]), "startTyre": car["tyre"]}
        elif self.last:
            rows = self.last["plans"]
            def missed(row):
                stop = next(iter(row.get("stops") or ()), None)
                return not self.in_pit and row.get("codexReason") and stop and stop["lap"] < frame["lap"]
            frame["previousPlans"] = {**self.last, "plans": [
                {**row, "codexExpired":True} if missed(row) else row for row in rows]}


def exit_passage(passage, codes, live):
    if passage is None:
        return None
    rank, ahead, behind, front_ms, rear_ms, waiting = passage
    return {"position":rank, "before":codes.get(ahead), "after":codes.get(behind),
            "aheadGapMs":front_ms, "behindGapMs":rear_ms, "waiting":bool(live and waiting)}


def pit_comparisons(raw):
    saved = {entry: (lap, rank, actual, entry, exit_ms)
             for lap, rank, actual, entry, exit_ms in raw.get("pitComparisons", [])}
    service = {at: {**({"serviceMs": ms} if ms else {}), **({"wingRepair": True} if wing else {}),
                    **({"penalty": True} if penalty else {})} for at,ms,wing,penalty in raw.get("pitService", [])}
    for entry, work in raw.get("pitWork", {}).items():
        service.setdefault(entry, {}).update(work)
    for entry, pair in raw.get("recordedScenarios", {}).items():
        service.setdefault(entry, {})["recordedScenarios"] = pair
    visits = raw.get("replayedVisits", [])
    results = []
    for lap, rank, actual, entry, exit_ms in visits:
        indexed = saved.pop(entry, None)
        # Early recorders split one continuous visit during a pause. The
        # recomputed entry must stay attached to its own physical exit.
        results.append({"lap": lap, "predicted": indexed[1] if indexed else None,
                        "recalculated": rank, "actual": actual, "entryMs": entry,
                        "exitMs": exit_ms, **service.get(entry, {})})
    for lap, rank, actual, entry, exit_ms in saved.values():
        if rank is None and any(v[3] < entry and (v[4] is None or entry <= v[4]) for v in visits):
            continue
        results.append({"lap": lap, "predicted": rank, "actual": actual, "entryMs": entry,
                        "exitMs": exit_ms, **service.get(entry, {})})
    return sorted(results, key=lambda row: row["entryMs"])


def live_frame(raw, stops=(), pit_ms=20000, proposal=None):
    pit_ms = raw.get("pitLossMs", pit_ms)
    rows = sorted(raw.get("cars", []), key=lambda c: c["position"])
    if not rows:
        return None
    codes = driver_codes(rows)
    rows = [dict(r, code=codes[r["slot"]]) for r in rows]
    me = next((r for r in rows if r["slot"] == raw["player"]), None)
    player = rows.index(me) if me and not raw["spectating"] else -1
    cars = [car_row(raw, c, c["code"]) for c in rows]
    colour_sectors(cars)
    weather = raw["weather"]
    wet = surface_for(weather)
    rain = RAIN[weather] if weather < len(RAIN) else "Unknown"
    flag = {1:"SC",2:"VSC",3:"FORMATION"}.get(raw["safety"], "YELLOW" if raw["yellow"] else "TRACK CLEAR")
    if me and me.get("flag") in (3,4):
        flag = "RED" if me["flag"] == 4 else ("YELLOW" if not raw["safety"] else flag)
    lap = me["lap"] if player >= 0 else rows[0]["lap"]
    on_grid = bool(me and raw["sessionType"] in (15,16,17,19,20) and lap == 1
                   and me.get("speed") == 0 and me.get("currentMs") == 0 and me.get("lastMs") == 0
                   and me.get("driverStatus") == 4 and not me["pit"]
                   and not any(e[1]=="LGOT" for e in raw["events"]))
    mode = "dnf" if me and me["result"] in (4,5,6,7) else "grid" if lap == 0 or on_grid or flag=="FORMATION" else "race"
    race = raw["sessionType"] in (15,16,17,19,20)
    if not race:
        best = min((c["bestMs"] for c in cars if c["bestMs"]), default=0)
        for i, c in enumerate(cars):
            c["gapMs"] = c["bestMs"]-best if c["bestMs"] and best else None
            prior = cars[i-1]["bestMs"] if i else 0
            c["intervalMs"] = c["bestMs"]-prior if c["bestMs"] and prior and c["bestMs"]>=prior else None
            c["change"] = None
    can_plan = bool(player >= 0 and me and me["result"] == 2 and race and raw["totalLaps"]>lap
                    and raw["totalLaps"]>1 and cars[player]["tyre"] and flag != "RED")
    estimates, forecast_wait = (forecast(raw, rows, me, wet, stops, pit_ms, proposal)
                                if can_plan and mode=="race" and weather<6 else (None, None))
    history = me.get("history", []) if me else []
    session = str(raw["uid"])+"/"+str(raw["epoch"])
    events = race_events(raw, codes, session)
    pace_ok = bool(player >= 0 and flag!="RED" and race and lap>0 and mode=="race")
    chase_avg, defend_avg = raw.get("lapBattles",(None,None))
    chase, defend = raw.get("gapTrends", (None, None))
    return {"source":"Live","session":session,"mode":mode,"lap":lap,"totalLaps":raw["totalLaps"], "isRace":race,"timeLeft":raw["timeLeft"],
            "trackId":raw["track"],"sessionName":SESSION[raw["sessionType"]] if raw["sessionType"]<len(SESSION) else "Unknown",
            "cars":cars,"player":player,"events":events,"flag":flag,"marshalZones":raw.get("marshalZones", []),
            "serviceForecast":raw.get("serviceForecast"),"serviceAverages":raw.get("serviceAverages"),
            "serviceTimes":raw.get("serviceTimes"),
            "boxNowPosition":raw.get("boxNowPosition"),"lastRejoin":raw.get("lastRejoin"),
            "pitLossMs":pit_ms,"gamePitPriorMs":raw.get("gamePitPriorMs"),"pitLossSamples":raw.get("pitLossSamples", 0),
            "neutralPitLoss":raw.get("neutralPitLoss"),
            "pitComparisons":pit_comparisons(raw),
            "lastPitExit":exit_passage(next(reversed(raw.get("exitPassages", {}).values()), None),
                                       codes, live=bool(me and me["result"] == 2)),
            "observedStints":[{"lap":end+1,"tyre":COMPOUNDS[new]} for (end,_),(_,new) in pairwise(me.get("stints",())) if end<255 and new in COMPOUNDS] if me else [],
            "canPlan":can_plan,"paused":raw["paused"],"scene":"",
            "paceHistory":[(i,ms,"Valid" if v&1 else "Invalid") for i,(ms,_,v) in enumerate(history,1) if ms and i<lap][-5:],
            "gamePitWindow":raw.get("gamePitWindow"), "gameRejoin":raw.get("gameRejoin"),
            "availableTyres":list(dict.fromkeys(s[0] for s in available_sets(me))) if me and me.get("tyreSets") else None,
            "fittedLife":fitted[3] if me and (fitted := fitted_set(me)) else None,
            "weather":{"rain":rain,"surface":("Dry","Damp","Standing water")[wet] if weather<6 else "Unknown",
                       "condition":("Wet" if wet else "Dry") if weather<6 else "Unknown",
                       "approximate":raw.get("forecastApproximate"),"trackTemp":raw.get("trackTemp"),"airTemp":raw.get("airTemp"),
                       "outlook":[{"minutes":n,"rain":RAIN[w],"chance":pct} for n,w,pct in raw.get("weatherOutlook",[]) if n>0]},
            "lapAnalysis":{"chase":displayed_battle(rows[player-1],me,chase_avg) if pace_ok and player else None,
                           "defend":displayed_battle(me,rows[player+1],defend_avg) if pace_ok and player+1<len(rows) else None},
            "forecast":estimates, "forecastWait":forecast_wait,"analysis":{"chase":live_pace(rows[player-1],me,chase,raw) if pace_ok and player else None,
                "defend":live_pace(me,rows[player+1],defend,raw) if pace_ok and player+1<len(rows) else None}}

