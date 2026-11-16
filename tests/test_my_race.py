import pytest
from fastapi.testclient import TestClient

import f125_core
from demo_strategy import Plan
from server import DNF_SECONDS, DURATION, GRID_SECONDS, LAPS, app, timing_snapshot


def test_quick_service_ranks_use_the_selected_laps_traffic():
    field = [('ME',0,'M',1,90000,[]), ('RIV',23000,'M',1,85000,[])]
    losses = [(19000,1),(25000,2)]
    forecast = f125_core.race_forecast(field,0,(2,6),(0,False,False),20000,[],quick_losses=[losses,losses])
    assert len(forecast['serviceRejoins']) == len(forecast['rejoins']) == 4
    assert forecast['serviceRejoins'][:2] == [[(1,19000,1),(2,25000,2)], [(2,19000,1),(2,25000,2)]]
    assert all(row == [(2,19000,1),(2,25000,2)] for row in forecast['serviceRejoins'][2:])
    first, second = forecast["rejoins"][:2]
    assert (first["before"], first["aheadGapMs"], first["after"], first["behindGapMs"]) == (None, None, "RIV", 3000)
    assert (second["before"], second["aheadGapMs"], second["after"], second["behindGapMs"]) == ("RIV", 2000, None, None)


def test_traffic_ahead_includes_the_three_second_boundary_only_ahead():
    field = [(code,gap,"M",1,90000,[]) for code,gap in
             (("ME",0),("OUT",16999),("EDGE",17000),("IN",18862),("BEHIND",20100))]
    forecast = f125_core.race_forecast(field,0,(2,6),(0,False,False),20000,[])
    assert forecast["trafficWindowMs"] == 3000
    for key in ("rejoins","tyreExits"):
        assert forecast[key][0]["trafficAhead"] == [("IN",1138),("EDGE",3000)]


def test_overcut_requires_a_rival_to_gain_by_delaying_their_stop():
    sets = [("H", 250, 20)]
    field = [(code, gap, "M", 5, 90000, []) for code, gap in (("ME",0),("RIV",100))]
    obs = [(row[0], sets, 0, False, False, None, []) for row in field]
    def outcomes(entries):
        forecast = f125_core.race_forecast(entries, 0, (3,16), (0,False,False), 20000, [],
                                           ([],sets,[("RIV",6)],None),(obs,None))
        return forecast["cutScenarios"]["H"][0]
    assert outcomes(field) == [0,5,5]
    assert outcomes([field[0], ("RIV",30000,*field[1][2:])]) == [0,0,5]


def test_lap_based_forecast_changes_target_and_discards_invalid_samples():
    first = timing_snapshot(0)["analysis"]
    assert first["chase"] == {"deltaMs":50, "lap":17, "laps":4, "leader":"ALO", "follower":"YOU"}
    assert first["defend"]["laps"] == 0
    exits = timing_snapshot(0)["forecast"]["rejoins"]
    assert len(exits) == 27-18
    assert exits[0] == {"position":15,"before":"BEA","after":"HAD","lossMs":12100,
                        "aheadGapMs":900,"behindGapMs":700,"trafficAhead":[("BEA",900),("OCO",2500)]}
    assert timing_snapshot(18)["analysis"]["chase"]["deltaMs"] == -300
    for offset in (6, 38, 47, 54, 72, 103):
        assert timing_snapshot(offset)["analysis"] == {"chase":None,"defend":None}
    assert timing_snapshot(108)["analysis"] == first


@pytest.mark.parametrize("stops", [[],[{"lap":0,"tyre":"H"}],[{"lap":27,"tyre":"H"}],
                                   [{"lap":21,"tyre":"Z"}],[{"lap":21,"tyre":"H"}]*2])
def test_invalid_grid_stops_are_rejected(stops):
    with pytest.raises(ValueError):
        Plan().confirm({"start":"M","stops":stops},0)


def test_socket_owns_the_plan_and_rejects_obsolete_edits(monkeypatch):
    clock = 0
    monkeypatch.setattr("server.demo_elapsed", lambda: clock)
    with TestClient(app) as client, client.websocket_connect("/ws/demo") as ws:
        def receive(predicate):
            for _ in range(30):
                result = ws.receive_json()
                if predicate(result):
                    return result
            pytest.fail("Expected frame never arrived")

        def command(data, predicate):
            ws.send_json(data)
            return receive(predicate)

        grid = receive(lambda f:f["mode"]=="grid")
        stops = [{"lap":9,"tyre":"M"},{"lap":15,"tyre":"H"},{"lap":20,"tyre":"I"}]
        edit = {"type":"confirm","start":"S","stops":stops,"token":grid["token"]}
        confirmed = command(edit,lambda f:f["plan"]["start"]=="S")
        assert confirmed["plan"]["stops"] == stops
        assert confirmed["cars"][confirmed["player"]]["tyre"] == "S"
        clock = GRID_SECONDS
        driving = receive(lambda f:f["mode"]=="race")
        rejected = command(edit,lambda f:"다시 선택" in f["notice"])
        assert rejected["plan"] == confirmed["plan"]
        change = dict(edit,token=driving["token"],stops=[{"lap":19,"tyre":"W"}])
        updated = command(change,lambda f:f["plan"]["stops"][-1]["lap"]==19)
        assert updated["plan"]["stops"] == [*stops[:2],{"lap":19,"tyre":"W"}]
        clock += DURATION * LAPS
        retired = receive(lambda f:f["mode"]=="dnf")
        assert retired["cars"][retired["player"]]["retired"] and retired["lap"] == 23
        denied = command(dict(change,token=retired["token"]),lambda f:"적용할 수 없음" in f["notice"])
        assert denied["plan"] == updated["plan"]
        clock += DNF_SECONDS
        reset = receive(lambda f:f["mode"]=="grid")
        assert reset["plan"] == Plan().wire() and reset["session"] == grid["session"] + 1



def test_native_forecast_responds_to_pace_gap_loss_and_weather():
    field = [("YOU", 0, "M", 12, 93000, [(10, 93900), (11, 93990)]),
             ("HAM", 11000, "H", 5, 94000, [])]

    def predict(entries=field, loss=12000, surface=0, neutral=False, lap=18, stops=()):
        return f125_core.race_forecast(entries, 0, (lap, 27), (surface, False, neutral), loss, stops)

    base = predict()
    assert base["rejoins"][0]["position"] == 2
    assert predict(loss=10000)["rejoins"][0]["position"] == 1
    assert predict(neutral=True)["rejoins"][0]["lossMs"] == 7200
    assert predict(entries=[field[0], ("HAM", 15000, *field[1][2:])])["rejoins"][0]["position"] == 1
    slower = [(*field[0][:-1], [(10, 94900), (11, 94990)]), field[1]]
    for original, changed in zip(base["plans"], predict(entries=slower)["plans"]):
        assert changed["remainingMs"] - original["remainingMs"] == 10 * 1000
    assert all(p["stop"][1] == "I" for p in predict(surface=1)["plans"])
    assert all(p["stop"][1] == "W" for p in predict(surface=2)["plans"])
    assert predict(stops=[(20,"H"),(25,"W")])["plans"][0]["remainingMs"] > base["plans"][0]["remainingMs"]
    assert all(p["stop"][0] == 26 for p in predict(lap=26)["plans"])
    with pytest.raises(ValueError):
        predict(lap=27)


def test_forecast_only_uses_completed_clean_laps_on_current_set():
    grid = timing_snapshot(0,"grid")
    assert grid["forecast"]["cleanSamples"] == 0 and not grid["paceHistory"]
    dry = timing_snapshot(0)
    assert dry["forecast"]["cleanSamples"] == 3
    assert all(n < dry["lap"] for n, _, _ in dry["paceHistory"])
    damp = timing_snapshot(54)
    assert damp["forecast"]["cleanSamples"] == 3
    assert damp["forecast"]["recommended"] == "B"
    assert damp["forecast"]["plans"][1]["stop"] == {"lap":21,"tyre":"I"}
    assert "ALO" not in timing_snapshot(107)["forecast"]["rivals"]
    assert timing_snapshot(107,"dnf")["forecast"] is None
