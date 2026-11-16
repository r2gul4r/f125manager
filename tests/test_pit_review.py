import pit_review
from pit_diagnosis import diagnose


def test_review_uses_only_retained_pre_entry_displays(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pit_review,
        "stop_observations",
        lambda *args: ({0: 55, 100: 120}, {}, [], {}, {}, None),
    )
    monkeypatch.setattr(pit_review, "recorded_passages", lambda *args: {})

    def sample(lap, at, target=12, branch=0, tick=40, visible=True):
        return pit_review.Sample(
            at=at,
            lap=lap,
            target=target,
            branch=branch,
            tick=tick,
            basis=lap,
            visible=visible,
            held=False,
            exit=pit_review.Exit(
                position=4, before="ALO", after="COR", aheadGapMs=638, behindGapMs=999
            ),
        )

    pit_review.save_samples(
        tmp_path,
        [
            sample(9, 250, 15),
            sample(9, 290, visible=False),
            sample(10, 300, visible=False),
            sample(10, 310, tick=56),
            sample(12, 499, branch=100),
            sample(12, 500, branch=100),
            sample(12, 501, branch=100),
        ],
    )
    stop = {"lap": 12, "entryMs": 500, "exitMs": 600, "actual": 3}
    review = pit_review.comparison(tmp_path, [stop], 1000)[0]
    a, b, c, d = review["forecasts"]
    assert (a["at"], a["target"], a["visible"]) == (250, 15, True)
    assert (b["at"], b["visible"]) == (300, False)
    assert c is None and d["at"] == 499 and d["behindGapMs"] == 999
    assert review["actual"]["position"] == 3


def test_rank_error_explained_by_measured_loss_and_frozen_rival_order():
    s = {
        "target": 12,
        "basis": 12,
        "position": 2,
        "before": "ALO",
        "after": "COR",
        "aheadGapMs": 650,
        "behindGapMs": 500,
        "lossMs": 18000,
        "rivalMargins": [("ALO", -650), ("COR", 500), ("HAD", 900), ("LEC", 3500)],
    }
    actual = {
        "position": 4,
        "before": "HAD",
        "after": "LEC",
        "aheadGapMs": 400,
        "behindGapMs": 1700,
    }
    stop = {"lap": 12, "measuredLossMs": 19300, "lossIncluded": True}
    review = diagnose(
        stop,
        [None, None, None, s],
        actual,
        [],
        {"COR": 2, "HAD": 3, "LEC": 5},
        {},
        None,
    )
    assert "2자리 뒤" in review["scores"][3]
    assert any("P2 → P4 · COR, HAD" in f for f in review["facts"])
    assert any("예상과 달리 내 앞" in f and "COR, HAD" in f for f in review["facts"])
    # The other scheduled lap can't be scored against this stop.
    s["target"] = 13
    review = diagnose(stop, [None, None, None, s], actual, [], {}, {}, None)
    assert review["scores"][3] is None and not any(
        "P2 → P4" in f for f in review["facts"]
    )


def test_clean_pace_and_events_are_evidence_not_a_pit_loss_label():
    early = {
        "target": 12,
        "basis": 10,
        "position": 1,
        "before": None,
        "after": "COR",
        "lapPaceMs": [("STA", 81000), ("COR", 80000)],
    }
    stop = {
        "lap": 12,
        "penalty": True,
        "wingRepair": True,
        "safetyChanged": True,
        "safetyStates": [0, 2],
        "serviceDelayed": True,
    }
    actual = {
        "position": 1,
        "before": None,
        "after": "COR",
        "aheadGapMs": None,
        "behindGapMs": 1200,
    }
    review = diagnose(
        stop,
        [None, early, None, dict(early, basis=12, behindGapMs=1500)],
        actual,
        ["COR"],
        {},
        {"STA": {10: 82100}, "COR": {10: 80000}},
        "STA",
    )
    assert any("1.100초 느렸음" in f for f in review["facts"])
    assert any("그린 → VSC" in f for f in review["facts"])
    assert "0.300초 크게" in review["scores"][3]
    assert "표본 제외" in review["learning"]
