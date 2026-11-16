"""Explain observed errors without treating hypothetical plans as race results."""


def _score(sample, actual, lap):
    if not sample or not actual or sample["target"] != lap:
        return None
    gaps = []
    changed = []
    for side, field, label in (
        ("before", "aheadGapMs", "앞"),
        ("after", "behindGapMs", "뒤"),
    ):
        if actual.get("neighboursKnown") is False:
            break
        predicted, observed = sample[side], actual[side]
        if predicted != observed:
            changed.append(f"{label} {predicted or '없음'} → {observed or '없음'}")
        elif (
            observed and sample.get(field) is not None and actual.get(field) is not None
        ):
            error = sample[field] - actual[field]
            gaps.append(
                f"{label} {observed} 간격 {abs(error) / 1000:.3f}초 "
                + ("크게" if error > 0 else "작게")
                if error
                else f"{label} {observed} 간격 일치"
            )
    diff = actual["position"] - sample["position"]
    rank = f"{abs(diff)}자리 " + ("뒤" if diff > 0 else "앞") if diff else "순위 일치"
    return " · ".join([rank, *changed, *gaps])


def _loss_effect(sample, stop, actual):
    loss, measured = sample.get("lossMs"), stop.get("measuredLossMs")
    if (
        loss is None
        or measured is None
        or stop.get("penalty")
        or sample.get("penaltyMs")
    ):
        return []
    delta = measured - loss
    lines = [
        f"타이어 교체 가정 피트 손실 {loss / 1000:.3f}초 · 실제 {measured / 1000:.3f}초"
    ]
    margins = sample.get("rivalMargins")
    if margins is None or any(ms in (0, delta) for _, ms in margins):
        return lines
    crossed = [code for code, ms in margins if min(delta, 0) < ms < max(delta, 0)]
    pos = sample["position"] + (len(crossed) if delta > 0 else -len(crossed))
    names = " · " + ", ".join(crossed) if crossed else ""
    lines.append(
        f"상대 움직임을 예측대로 두고 실측 손실만 적용하면 P{sample['position']} → P{pos}{names}"
    )
    if actual and sample["position"] != actual["position"]:
        remain = abs(actual["position"] - pos)
        lines.append(
            f"손실 시간 차이를 반영해도 {remain}자리 차이 남음"
            if remain
            else "손실 시간 차이만 반영해도 실제 복귀 순위와 일치"
        )
    return lines


def _pace_difference(forecasts, lap, clean, player):
    for sample in reversed(forecasts[:-1]):
        if not sample or sample["target"] != lap or sample.get("held"):
            continue
        basis = sample["basis"]
        estimates = dict(sample.get("lapPaceMs") or ())
        if player not in estimates or basis not in clean.get(player, {}):
            continue
        for rival in (sample["before"], sample["after"]):
            if rival not in estimates or basis not in clean.get(rival, {}):
                continue
            change = (clean[player][basis] - clean[rival][basis]) - (
                estimates[player] - estimates[rival]
            )
            if change:
                return (
                    f"L{basis} 유효랩에서 {rival} 대비 내 페이스가 예상보다 {abs(change) / 1000:.3f}초 "
                    + ("느렸음" if change > 0 else "빨랐음")
                )
    return None


def diagnose(stop, forecasts, actual, pitted, ranks, clean, player):
    lap = stop["lap"]
    scores = [_score(s, actual, lap) for s in forecasts]
    sample = forecasts[-1]
    facts = []
    if stop.get("wingRepair"):
        facts.append("실제 작업에 앞날개 교체 포함")
    elif stop.get("repairs"):
        facts.append("차체 손상 감소 기록 있음")
    if stop.get("safetyChanged"):
        names = ("그린", "SC", "VSC", "포메이션")
        flags = [
            names[i] if 0 <= i < len(names) else "기타"
            for i in stop.get("safetyStates", [])
        ]
        facts.append("피트 중 트랙 상태 변경" + " · " + " → ".join(flags))
    if stop.get("penalty"):
        facts.append("페널티 스톱")
    if stop.get("serviceDelayed"):
        facts.append("같은 작업보다 정차 지연 · 크루 실수 여부 미확인")
    matching = sample is not None and sample["target"] == lap
    if matching:
        relevant = {sample["before"], sample["after"]}
        if actual:
            relevant.update((actual["before"], actual["after"]))
            margins = sample.get("rivalMargins") or []
            for was_ahead, label in (
                (False, "예상과 달리 내 앞에서 복귀"),
                (True, "예상과 달리 내 뒤에서 복귀"),
            ):
                changed = [
                    code
                    for i, (code, _) in enumerate(margins)
                    if code in ranks
                    and (i < sample["position"] - 1) == was_ahead
                    and (ranks[code] < actual["position"]) != was_ahead
                ]
                if changed:
                    facts.append(label + " · " + ", ".join(changed))
                    relevant.update(changed)
        names = [code for code in pitted if code in relevant]
        if names:
            facts.append("내 피트 구간에 함께 피트한 라이벌 · " + ", ".join(names))
        facts.extend(_loss_effect(sample, stop, actual))
    if not matching:
        recorded = stop.get("recordedScenarios")
        if recorded and actual:
            rank, ms, _ = recorded[0]
            facts.append(
                f"당시 엔진 기록 · 타이어 교체 예상 P{rank}, 손실 {ms / 1000:.3f}초 · 실제 P{actual['position']}"
            )
            if stop.get("measuredLossMs") is not None:
                facts.append(f"실측 피트 손실 {stop['measuredLossMs'] / 1000:.3f}초")
        else:
            facts.append("진입 랩을 대상으로 한 직전 예측 기록 없음")
    elif actual and sample["position"] != actual["position"]:
        facts.append("순위 차이의 단일 원인은 확정할 수 없음")
    elif actual and stop.get("measuredLossMs") is None:
        facts.append("피트 손실 실측 없음 · 갭 차이의 원인 미확정")
    pace = _pace_difference(forecasts, lap, clean, player)
    if pace:
        facts.append(pace)
    learning = (
        "같은 조건의 "
        + ("앞날개 교체" if stop.get("wingRepair") else "타이어 교체")
        + " 손실 표본에 포함"
        if stop.get("lossIncluded")
        else "피트 손실 보정 표본 제외"
    )
    validation = sample.get("validation") if matching else None
    if validation:
        promoted, n, base, candidate = validation
        learning += f" · 예측 당시 검증 {n}경기"
        if n and base is not None and candidate is not None:
            learning += f" (평균 방식 오차 {base / 1000:.3f}초 / 중앙값 방식 {candidate / 1000:.3f}초)"
        learning += " · 중앙값 적용" if promoted else " · 평균 방식 유지"
    return {"scores": scores, "facts": facts, "learning": learning}
