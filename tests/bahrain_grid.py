"""Replay Bahrain FP1 and the stationary race grid. Pass --real-codex for one external turn."""

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f125_core
from gp_advisor import AdvisorView, GpAdvisor


async def check(directory, real):
    root = Path("data/recordings")
    race = root / "1794711347679644-450152b3f1f6e1fc"
    clock = int(race.name.split("-")[0]) // 1000
    reader = f125_core.Replay(race)
    raw = reader.advance(17000)
    view = AdvisorView(GpAdvisor(directory), replay=True)
    await view.prepare(raw, root, clock)
    grid = view.render(raw)
    setup = grid["preRace"]
    assert grid["mode"] == "grid" and grid["advisor"]["available"]
    assert setup["playerLaps"] == 0 and setup["fieldLaps"] == 119
    assert "fuelKg" not in setup and "kgPerLap" not in grid["practiceEvidence"]
    assert {p["start"] for p in setup["plans"] if p["modelMs"] == setup["plans"][0]["modelMs"]} == {"M", "S"}
    assert all(setup["tyres"][t]["pairs"] for t in "SMH")
    print(json.dumps(setup, ensure_ascii=False), flush=True)
    if real:
        grid["token"] = "bahrain-grid"
        view.command(
            {"type": "askCodex", "token": grid["token"]}, raw, grid, None, clock + 17000
        )
        await view.task
        grid = view.render(raw)
        result = grid["advisor"]
        assert result.get("plan"), result
        grid["token"] = "bahrain-grid"
        plan = view.command(
            {
                "type": "applyCodex",
                "token": grid["token"],
                "id": result["id"],
                "stops": result["plan"]["stops"],
            },
            raw,
            grid,
            None,
            clock + 17000,
        )
        print(
            json.dumps(
                {"plan": plan.wire(), "reason": result["reason"]}, ensure_ascii=False
            ),
            flush=True,
        )
    assert view.render(reader.advance(25000))["mode"] == "race"


if __name__ == "__main__":
    with TemporaryDirectory() as scratch:
        asyncio.run(check(scratch, "--real-codex" in sys.argv))
