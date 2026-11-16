import asyncio
import json
from types import SimpleNamespace

import pytest

import gp_advisor as module
from demo_strategy import Plan
from gp_advisor import GpAdvisor, gp_key


def test_gp_continuity_and_validated_commit(monkeypatch, tmp_path):
    calls = []
    turn_options = []

    class Sdk:
        def __init__(self, config):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def thread_start(self, **opts):
            self.id = f"thread-{len(calls)}"
            calls.append(("start", self.id))
            return self

        async def thread_resume(self, thread_id, **opts):
            calls.append(("resume", thread_id))
            self.id = thread_id
            return self

        async def run(self, facts, **opts):
            turn_options.append((opts.get("model"), opts.get("effort")))
            snapshot = json.loads(facts)
            if snapshot["requestedPlans"] == ["B"]:
                assert snapshot["lap"] == 7 and set(snapshot["keepPlans"]) == {"A", "C"}
                assert opts["output_schema"]["required"] == ["B"]
                return SimpleNamespace(error=None, final_response=json.dumps(
                    {"B":{"lap":7,"tyre":"H","reason":"renewed"}}))
            assert snapshot["lap"] == 2
            return SimpleNamespace(
                error=None, final_response=json.dumps({key:{"lap":lap,"tyre":"M","reason":"test"} for key,lap in zip("ABC",(7,6,8))})
            )

    monkeypatch.setattr(module, "AsyncCodex", Sdk)
    raw = {"format": 2026, "track": 3, "seasonLink": 10, "weekendLink": 20, "uid": "123"}
    gp = gp_key(raw, False)
    assert gp == gp_key({**raw, "uid": "124"}, False)
    assert gp != gp_key(raw, True)
    other = gp_key({**raw, "weekendLink": 21}, False)
    frame = {
        "session": "123/1",
        "lap": 2,
        "totalLaps": 29,
        "trackId": 3,
        "flag": "TRACK CLEAR",
        "availableTyres": ["M", "H"],
        "weather": {"surface": "Dry"},
        "fittedLife": 7,
        "gamePitWindow": [7, 8],
        "pitLossMs": 20000,
        "pitLossSamples": 0,
        "player": 0,
        "cars": [
            {
                "code": "YOU",
                "pit": False,
                "position": 4,
                "tyre": "S",
                "age": 2,
                "gapMs": 500,
                "lastMs": 90000,
            }
        ],
        "forecast": {"plans": []},
        "token": "L2",
    }

    async def run():
        await GpAdvisor(tmp_path).propose(gp, frame, 100)
        service = GpAdvisor(tmp_path)
        async def available():
            return [{"id": "test-model", "efforts": ["medium", "high"]}]
        monkeypatch.setattr(service, "models", available)
        with pytest.raises(ValueError):
            await service.configure("test-model", "unsupported")
        await service.configure("test-model", "high")
        assert GpAdvisor(tmp_path).preferences() == ("test-model", "high")
        reply = await service.propose(gp, frame, 200)
        assert turn_options == [(None, None), ("test-model", "high")]
        with pytest.raises(ValueError, match="이전"):
            await service.propose(gp, frame, 99)
        await service.propose(other, frame, 200)
        assert calls == [
            ("start", "thread-0"),
            ("resume", "thread-0"),
            ("start", "thread-2"),
        ]
        assert reply["choices"]["B"]["lap"] == 6
        original = Plan("M", ((12,"H"),))
        service.commit(gp, "123/1", original, reply["id"], (10,1000,"A"))
        assert service.restore_decision(gp,"123/2",12,0) == (original,"A")
        assert service.restore_decision(gp,"123/3",9,0) == (None,None)
        assert service.saved_plan(other, frame["session"]) is None
        later = {**frame, "lap":7}
        first, second = await asyncio.gather(*(service.propose(gp, later, 300, "B", reply) for _ in range(2)))
        assert len(calls) == 4 and first == second
        assert first["choices"]["B"] == {"lap":7,"tyre":"H","reason":"renewed"}
        assert all(first["choices"][k] == reply["choices"][k] for k in "AC")
        assert GpAdvisor(tmp_path).saved_choices(gp, later) == first
        assert service.saved_plan(gp, frame["session"]) == original

    asyncio.run(run())
