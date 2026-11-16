import asyncio
from types import SimpleNamespace

import pytest

from game_mfd import RacePitSync, TyreRow, set_next_tyre
from live_timing import recommend_plan


class PitPanel:
    def __init__(self, choices="SMHIW"):
        self.choices = choices
        self.row = TyreRow(1, "M")
        self.keys = []
        self.transient = None

    def read(self):
        if self.transient:
            row, self.transient = self.transient, None
            return row
        return self.row

    async def press(self, key):
        self.keys.append(key)
        if key == "down":
            self.row = TyreRow(0, self.row.tyre)
        else:
            assert self.row.down == 0
            index = self.choices.index(self.row.tyre) + (1 if key == "right" else -1)
            self.row = TyreRow(0, self.choices[index % len(self.choices)])
            self.transient = TyreRow(0, "W")


def test_select_compound_only_on_verified_tyre_row():
    panel = PitPanel()
    for target in ("H", "S", "M"):
        asyncio.run(set_next_tyre(target, lambda: True, lambda: panel))
        assert panel.read().tyre == target
    assert panel.keys == ["down", "right", "left", "left", "right"]
    with pytest.raises(ValueError):
        asyncio.run(set_next_tyre("S", lambda: False, lambda: panel))
    assert len(panel.keys) == 5


def test_unavailable_dry_compound_restores_observed_selection():
    panel = PitPanel("SMIW")
    with pytest.raises(ValueError, match="M 복원 확인"):
        asyncio.run(set_next_tyre("H", lambda: True, lambda: panel))
    assert panel.row == TyreRow(0, "M")
    assert panel.keys == ["down", "right", "left"]


def test_reselection_waits_for_inflight_key_and_only_runs_latest_plan():
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        sent = []

        async def send(tyre, valid):
            sent.append(tyre)
            if len(sent) == 1:
                started.set()
                await release.wait()
                assert not valid()
                raise ValueError("superseded")
            assert valid()

        car = {"slot":0, "result":2, "pit":False, "pitStops":0, "lap":2}
        raw = {"uid":"race", "epoch":0, "ageMs":0, "player":0, "cars":[car]}
        sync = RacePitSync(lambda: raw, send)
        frame = {"isRace":True, "mode":"race", "lap":2}
        sync.submit(raw, frame, SimpleNamespace(stops=[(9, "M")]))
        await started.wait()
        for tyre in ("S", "H"):
            sync.submit(raw, frame, SimpleNamespace(stops=[(9, tyre)]))
        release.set()
        await sync.task
        assert sent == ["M", "H"]
        assert sync.message.endswith("다음 타이어 H")

    asyncio.run(run())


def test_sync_follows_observed_stop_and_never_sends_from_replay():
    car = {
        "slot": 0,
        "lap": 5,
        "result": 2,
        "pit": False,
        "pitStops": 0,
        "compound": 16,
    }
    raw = {"uid": "1", "epoch": 0, "ageMs": 0, "player": 0, "cars": [car]}
    sent = []

    async def transmit(tyre, valid):
        assert valid()
        sent.append(tyre)

    sync = RacePitSync(lambda: raw, transmit)
    frame = {"isRace": True, "mode": "race", "lap": 5}
    plan = SimpleNamespace(stops=[(9, "M"), (20, "H")])

    async def run():
        sync.submit(dict(raw, handoff=True), frame, plan)
        assert sync.task is None
        sync.submit(raw, frame, plan)
        await sync.task
        car.update(lap=9, pit=True, pitStops=1)
        sync.observe(raw)
        assert sent == ["M"]
        car.update(pit=False, compound=17)
        sync.observe(raw)
        await sync.task
        assert sent == ["M", "H"]

    asyncio.run(run())


def test_probability_of_improving_position_precedes_time():
    def plan(name, ranks, ms, shortfall=0):
        return {
            "id": name,
            "scenarioRanks": ranks,
            "remainingMs": ms,
            "lifeShortfall": shortfall,
        }

    plans = [
        plan("A", [6, 8, 8, 9, 9], 100),
        plan("B", [7, 7, 7, 8, 8], 200),
        plan("C", [4] * 5, 90, 2),
    ]
    plans[2]["tyreIssues"] = [(9,10,"S","life")]
    assert recommend_plan(plans, 8) == "C"
    plans[2]["tyreIssues"] = [(9,10,"S","stock")]
    assert recommend_plan(plans, 8) == "B"
    assert recommend_plan(plans, 1) == "B"  # Leading: expected position breaks the tie.
