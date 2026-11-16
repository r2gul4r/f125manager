"""Wire-level regressions. Use an ephemeral listener, including when the real game is running."""
import socket
import struct
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

import f125_core
from live_timing import colour_sectors, connection_state, live_pace
from server import app


def packets(year, uid=123, frame=10):
    modern = year == 2026
    sizes = {1:926 if modern else 753, 2:1399 if modern else 1285,
             4:1470 if modern else 1284, 6:1448 if modern else 1352,
             7:1445 if modern else 1239, 11:1460, 0:1325 if modern else 1349}
    out = {i:bytearray(n) for i,n in sizes.items()}
    for i,b in out.items():
        struct.pack_into("<HBBBBBQfIIBB", b, 0,year,25,1,0,1,i,uid,1.0,frame,frame,1,255)
    s=out[1]
    s[32]=52
    struct.pack_into("<H", s,33,5900)
    s[35:37]=bytes((15,7))
    out[4][29]=2
    for slot, name in enumerate((b"Max Verstappen",b"Lewis Hamilton")):
        part = 30+slot*(60 if modern else 57)+(10 if modern else 7)
        out[4][part:part+len(name)] = name
        out[4][part+32]=1
        lap=29+57*slot
        struct.pack_into("<I",out[2],lap,91200-400*slot)
        struct.pack_into("<H",out[2],lap+14,2000*slot)
        struct.pack_into("<H",out[2],lap+17,2000*slot)
        struct.pack_into("<f",out[2],lap+20,2950)
        out[2][lap+32:lap+34]=bytes((slot+1,7))
        out[2][lap+43:lap+46]=bytes((slot+1,4,2))
        status=29+(59 if modern else 55)*slot
        out[7][status+26:status+28]=bytes((16+slot,6))
        struct.pack_into("<H",out[6],29+(59 if modern else 60)*slot,230+slot)
        struct.pack_into("<fff",out[0],29+(54 if modern else 60)*slot,100+slot,0,200+slot)
    h=out[11]
    h[29:33]=bytes((1,6,1,6))
    struct.pack_into("<IH B H B H B B",h,36+5*14,90800,31000,0,30000,0,29800,0,15)
    h[1436:1439]=bytes((255,18,17))
    return out


def test_live_battle_uses_current_gap_and_skips_pit_laps():
    front = {"slot":1, "code":"BOT", "lap":4, "age":3, "pit":False, "result":2, "lastMs":100000, "gapMs":20000}
    me = dict(front, slot=2, code="HAM", intervalMs=22583, lastMs=121477, gapMs=42583)
    raw = {"player":2, "pitComparisons":[(2, None, 21, 10, 40)]}
    trend = (1, 2, 200, 30000)
    pace = live_pace(front, me, trend, raw)
    assert (pace["deltaMs"], pace["laps"], pace["gapMs"]) == (2000, 11, 22583)
    widening = live_pace(front, me, (1, 2, -150, 30000), raw)
    assert (widening["deltaMs"], widening["laps"]) == (-1500, None)
    assert live_pace(front, dict(me, intervalMs=950, gapMs=20950), trend, raw)["laps"] == 0
    assert live_pace(front, dict(me, intervalMs=200), trend, raw) is None
    assert live_pace(front, dict(me, intervalMs=0), trend, raw) is None
    assert live_pace(front, dict(me, intervalValid=False), trend, raw) is None
    assert live_pace(front, me, None, raw) is None


def test_sector_colours_compare_valid_current_and_completed_sector_times():
    cars = [
        {"personal": [105, 95, 120], "liveSectors": [100, 98, 120], "sectors": [0, 0, 120],
             "sectorEligible": [True, True, True]},
        {"personal": [90, 100, 125], "liveSectors": [88, 0, 119], "sectors": [0, 0, 119],
             "sectorEligible": [True, True, False]},
    ]
    colour_sectors(cars)
    assert [c["sectorStatus"] for c in cars] == [
        ["personal", "normal", "fastest"], ["fastest", "pending", "pending"]]


@pytest.mark.parametrize("year",[2025,2026])
def test_game_socket_to_dashboard(year,monkeypatch):
    monkeypatch.setenv("F125_UDP_PORT","0")
    with TestClient(app) as client, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
        async def mfd_stub(tyre, valid):
            assert tyre == "S" and valid()
        app.state.game_sync.send = mfd_stub
        address=("127.0.0.1",app.state.udp.port)
        def send(payload):
            sender.sendto(payload,address)
        with client.websocket_connect("/ws/live") as ws:
            assert ws.receive_json()["status"] == "Waiting for UDP"
            wire=packets(year)
            send(wire[1][:-1])
            for p in wire.values():
                send(p)
            def receive(match):
                for _ in range(40):
                    msg=ws.receive_json()
                    if match(msg):
                        return msg
                pytest.fail("Expected live snapshot")
            msg=receive(lambda m:m["frame"] and m["frame"]["forecast"] and m["frame"]["cars"][1]["bestMs"])
            f=msg["frame"]
            assert msg["udp"]["rejected"]==1 and msg["udp"]["format"]==year
            assert (f["sessionName"],f["totalLaps"],f["player"],f["lap"])==("Race",52,1,7)
            me=f["cars"][1]
            assert (me["code"],me["speed"],me["tyre"],me["world"])==("HAM",231,"M",[101,201])
            assert me["phase"]==.5 and me["sectors"]==[31000,30000,29800]
            def event(code, fields):
                packet = bytearray(45)
                packet[:29] = wire[2][:29]
                packet[6] = 3
                packet[29:33] = code
                packet[33:33 + len(fields)] = bytes(fields)
                send(packet)

            event(b"PENA", (4, 4, 1, 0, 5, 6, 0))
            event(b"PENA", (4, 4, 1, 0, 5, 6, 0))
            event(b"PENA", (4, 17, 0, 255, 3, 7, 0))
            event(b"PENA", (5, 12, 1, 255, 0, 7, 0))
            event(b"OVTK", (0, 2))
            event(b"STLG", (3,))
            event(b"OVTK", (0, 1))
            event(b"DTSV", (0,))
            recent = receive(lambda m: m["frame"]["events"] and
                             m["frame"]["events"][0]["label"] == "드라이브스루 이행")["frame"]["events"]
            assert [(e["driver"], e["label"], e["detail"]) for e in recent] == [
                ("VER", "드라이브스루 이행", ""), ("VER", "추월", "상대 HAM"),
                ("HAM", "경고", "황기 무시"), ("VER", "시간 페널티 3초", "피트레인 과속"),
                ("HAM", "시간 페널티 5초", "경미한 충돌 · 상대 VER")]
            assert recent[-1]["lap"] == 6
            assert len({e["id"] for e in recent}) == len(recent)
            event(b"BUTN", struct.pack("<I", (1 << 21) | 1))
            event(b"BUTN", struct.pack("<I", 1 << 21))
            event(b"BUTN", struct.pack("<I", 0))
            event(b"BUTN", struct.pack("<I", 1 << 20))
            actions = []
            for _ in range(25):
                actions.extend(ws.receive_json()["wheelKeys"])
                if "udp/1" in actions:
                    break
            assert actions == ["udp/2", "udp/1"]
            mic = app.state.microphone
            assert client.get("/api/settings/microphone").json()["enabled"] is False
            seen = []
            with monkeypatch.context() as patch:
                patch.setattr(mic, "press", lambda: seen.append(3) is None)
                event(b"BUTN", struct.pack("<I", 1 << 22))
                event(b"BUTN", struct.pack("<I", 0))
                event(b"BUTN", struct.pack("<I", 1 << 20))
                actions = []
                for _ in range(25):
                    actions.extend(ws.receive_json()["wheelKeys"])
                    if "udp/1" in actions:
                        break
                assert seen == [3] and actions == ["udp/1"]
            event(b"BUTN", struct.pack("<I", 1 << 22))
            assert "udp/3" in receive(lambda m: "udp/3" in m["wheelKeys"])["wheelKeys"]
            assert f["analysis"]["chase"]["deltaMs"]==400
            assert f["lapAnalysis"]["chase"]["deltaMs"]==400
            assert f["lapAnalysis"]["chase"]["laps"]==3
            # A 1.5 s gain inside the same lap changes the observed interval,
            # while the previous clean lap still governs the displayed forecast.
            next_lap=bytearray(wire[2])
            struct.pack_into("<I",next_lap,23,11)
            for offset in (14,17):
                struct.pack_into("<H",next_lap,29+57+offset,500)
            send(next_lap)
            inside=receive(lambda m:m["frame"]["cars"][1]["intervalMs"]==500)["frame"]
            assert inside["lapAnalysis"]["chase"]["laps"]==0
            struct.pack_into("<I",next_lap,23,12)
            for offset in (14,17):
                struct.pack_into("<H",next_lap,29+57+offset,1200)
            send(next_lap)
            later=receive(lambda m:m["frame"]["cars"][1]["intervalMs"]==1200)["frame"]
            assert later["lapAnalysis"]["chase"]==dict(f["lapAnalysis"]["chase"],gapMs=1200)
            assert len(f["forecast"]["rejoins"])==45
            ws.send_json({"type":"confirm","token":f["token"],"start":"M","stops":[{"lap":35,"tyre":"S"}]})
            receive(lambda m:m["frame"]["plan"]["stops"]==[{"lap":35,"tyre":"S"}])
            zone_packet=packets(year,frame=11)[1]
            zones=[(.0625,-1),(.125,3),(.1875,1),(.375,2),(.875,3)]
            zone_packet[47]=len(zones)
            for i,(start,flag) in enumerate(zones):
                struct.pack_into("<fb",zone_packet,48+i*5,start,flag)
            send(zone_packet)
            local=receive(lambda m:m["frame"]["flag"]=="YELLOW")["frame"]
            assert local["marshalZones"]==[list(z) for z in zones]
            struct.pack_into("<I",zone_packet,23,12)
            zone_packet[57]=zone_packet[72]=0
            send(zone_packet)
            cleared=receive(lambda m:m["frame"]["flag"]=="TRACK CLEAR")["frame"]
            assert all(flag!=3 for _,flag in cleared["marshalZones"])
            send(packets(year,frame=9)[2])
            send(packets(year,999)[1])
            send(wire[2])  # delayed packet from the abandoned session
            pending=receive(lambda m:m["status"]=="Waiting for timing")
            assert pending["frame"] is None
            for p in packets(year,999,11).values():
                send(p)
            reset=receive(lambda m:m["frame"] and m["frame"]["session"]!=f["session"])
            assert reset["frame"]["plan"]["stops"]==[]


def test_socket_lifecycle_and_stream_age():
    rx=f125_core.UdpReceiver("127.0.0.1",0)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.sendto(packets(2026)[2],("127.0.0.1",rx.port))
        deadline=monotonic()+2
        while rx.snapshot()["ageMs"] is None and monotonic()<deadline:
            sleep(.01)
        raw=rx.snapshot()
        assert raw["ageMs"] is not None
        assert connection_state(dict(raw,ageMs=2001))=="Stale data"
        assert connection_state(dict(raw,ageMs=10001))=="UDP disconnected"
        with pytest.raises(OSError):
            f125_core.UdpReceiver("127.0.0.1",rx.port)
    port=rx.port
    rx.close()
    f125_core.UdpReceiver("127.0.0.1",port).close()


@pytest.mark.parametrize("year", [2025, 2026])
def test_game_strategy_weather_and_distance_samples(year,monkeypatch,tmp_path):
    from live_timing import live_frame

    monkeypatch.setenv("F125_UDP_PORT","0")
    monkeypatch.setenv("F125_RECORDING_DIR",str(tmp_path))
    wire=packets(year)
    session=wire[1]
    session[32]=16
    session[682:685]=bytes((10,10,2))
    session[155]=2
    session[156:164]=bytes((15,4,3,28,0,25,0,95))
    session[164:172]=bytes((1,1,5,28,0,25,0,99))  # different session
    struct.pack_into("<ff",session,745,1500,3600)
    sets=bytearray(231)
    sets[:29]=session[:29]
    sets[6]=12
    sets[29]=1
    for i,(code,available,life) in enumerate([(17,1,6),(18,1,15),(7,1,15),(16,0,20)]):
        start=30+10*i
        sets[start:start+10]=struct.pack("<BBBBBBBhB",code,code,5,available,15,life,15,100,i==0)
    with TestClient(app) as client, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
        address=("127.0.0.1",app.state.udp.port)
        for datagram in [session,wire[4],wire[2],wire[7],wire[11],sets,wire[6]]:
            sender.sendto(datagram,address)
        deadline=monotonic()+2
        while not app.state.udp.analysis()["samples"] and monotonic()<deadline:
            sleep(.01)
        raw=app.state.udp.snapshot()
        f=live_frame(raw)
        assert f["gamePitWindow"]==(10,10) and f["gameRejoin"]==2
        assert f["availableTyres"]==["H","I"] and f["fittedLife"]==6
        assert f["weather"]["outlook"]==[{"minutes":4,"rain":"Light rain","chance":95}]
        assert f["cars"][1]["miniProgress"]==[8,5,0]
        assert f["forecast"]["plans"][0]["stop"]=={"lap":10,"tyre":"I"}
        dry=live_frame(dict(raw,weatherOutlook=[]))
        assert dry["forecast"]["plans"][0]["stop"]=={"lap":12,"tyre":"H"}
        assert live_frame(dict(raw,weatherOutlook=[],gamePitWindow=(7,7)))["forecast"]==dry["forecast"]
        assert dry["forecast"]["plans"][0]["remainingMs"]!=f["forecast"]["plans"][0]["remainingMs"]
        samples=client.get("/api/analysis/live").json()["samples"]
        assert samples[0][:2]==[7,16] and samples[0][2][:2]==[2950,231]
        assert client.get("/api/analysis/not-a-recording").status_code==404


@pytest.mark.parametrize("year", [2025, 2026])
def test_line_crossing_and_held_forecast(year, monkeypatch):
    monkeypatch.setenv("F125_UDP_PORT", "0")
    with TestClient(app) as client, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        address = ("127.0.0.1", app.state.udp.port)
        wire = packets(year)
        leader, player = 29, 29 + 57
        wire[2][leader + 33] = 8
        struct.pack_into("<f", wire[2], leader + 20, 40)
        struct.pack_into("<f", wire[2], player + 20, 5900.75)
        for key in [1, 4, 7, 11, 2]:
            sender.sendto(wire[key], address)
        with client.websocket_connect("/ws/live") as ws:
            def until(matches):
                for _ in range(40):
                    message = ws.receive_json()
                    if message["frame"] and matches(message):
                        return message["frame"]
                pytest.fail("Expected forecast state")

            live = until(lambda m: m["frame"]["boxNowPosition"] == 2)
            assert [p["id"] for p in live["forecast"]["plans"]] == ["A", "B", "C"]
            session = packets(year, frame=11)[1]
            session[43] = 1
            sender.sendto(session, address)
            held = until(lambda m: m["status"] == "Paused")
            assert held["forecast"] == live["forecast"] and held["boxNowPosition"] == 2
            assert held["lap"] == 7 and held["canPlan"]
            session[43] = 0
            struct.pack_into("<I", session, 23, 12)
            sender.sendto(session, address)
            # Now the leader has passed the player on track: a genuine full lap.
            struct.pack_into("<I", wire[2], 23, 13)
            struct.pack_into("<f", wire[2], player + 20, 25)
            sender.sendto(wire[2], address)
            updated = until(lambda m: m["status"] == "Live" and m["frame"]["boxNowPosition"] is None)
            assert updated["forecast"] is None and "predictionLap" not in updated
            assert updated["previousPlans"]["plans"] == live["forecast"]["plans"]


def test_current_sector_clock_and_public_stint_age():
    from live_timing import current_tyre, running_pace

    car = {"lap":3,"lastMs":90000,"currentMs":49000,"distance":3000,"pit":False,
           "splits":[34000,0],"history":[(90000,[30000]*3,15)]*2}
    assert running_pace(car,6000,(),(2000,4000)) == (94000,True)
    assert running_pace(dict(car,driverStatus=3),6000,(),(2000,4000)) == (90000,False)
    car.update(stints=[(1,16),(255,18)],tyreDataPublic=True)
    assert current_tyre(car) == ('H',1)
    assert current_tyre(dict(car,tyreDataPublic=False)) == ('H',None)


def test_partial_sector_uses_clean_history_and_respects_elapsed_clock():
    from live_timing import running_pace

    car = {"lap": 4, "lastMs": 120000, "currentMs": 52000, "distance": 3000,
           "pit": False, "splits": [30000, 0], "slowLaps": [3],
           "history": [(90000, [30000]*3, 15), (90000, [30000]*3, 15),
                       (120000, [40000]*3, 15)]}
    def estimate(**changes):
        return running_pace(dict(car, **changes), 6000, (), (2000, 4000))

    assert estimate() == (90000, True)
    assert estimate(currentMs=65000) == (95000, True)
    assert estimate(slowLaps=[3, 4]) == (97000, True)


def test_pit_and_classification_costs_use_each_cars_observations():
    entries=[('ME',0,'M',4,90000,[]),('RIV',15000,'M',4,90000,[])]
    def simulate(penalty=0,serve=False,committed=False,paid=None,delta=0):
        stock=[('H',0,20)]
        inputs=[('ME',stock,penalty,serve,False,None,[]),
                ('RIV',[('H',delta,20)],0,False,committed,paid,[])]
        return f125_core.race_forecast(entries,0,(4,12),(0,False,True),20000,[],
                    ([],stock,[('RIV',10)],None),(inputs,11000))
    base=simulate()
    penalised=simulate(5,True)
    assert base['rejoins'][0]['lossMs']==11000
    assert penalised['rejoins'][0]['lossMs']==16000
    assert simulate(5)['rejoins'][0]['lossMs']==11000
    assert penalised['plans'][0]['remainingMs']-base['plans'][0]['remainingMs']==5000
    assert simulate(5,True,True,0)['rejoins'][0]['position']==1
    assert simulate(5,True,True,11000)['rejoins'][0]['position']==2
    assert simulate(delta=720)['rivals']['RIV']['overcutMs']-base['rivals']['RIV']['overcutMs']==720


def test_strategy_reports_each_uncovered_lap_range():
    field = [('ME',0,'S',0,90000,[]),('RIV',1000,'M',1,90000,[])]
    stock = [('H',0,2)]
    plan = f125_core.race_forecast(field,0,(1,12),(0,False,False),20000,[],
        ([],stock,[('ME',2)],None),([],None),(5,'H'))['plans'][-1]
    assert plan['tyreIssues'] == [(3,4,'S','life'), (7,12,'H','life')]
    assert plan['lifeShortfall'] == 8


def test_historical_compound_degradation_skips_flagged_and_pit_laps():
    from live_timing import compound_slopes
    car={"lap":8,"stints":[(4,16),(255,17)],"history":[(t,[],1) for t in
         (130000,90000,90100,160000,140000,89500,89700)]}
    assert compound_slopes(car,{4,5}) == [("S",100,1),("M",200,1)]

@pytest.mark.parametrize("year",[2025,2026])
def test_game_pit_advice_cannot_override_model_results(year,monkeypatch):
    from live_timing import live_frame
    monkeypatch.setenv("F125_UDP_PORT","0")
    with TestClient(app), socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
        wire=packets(year)
        wire[1][682:685]=bytes((8,9,1))
        address=("127.0.0.1",app.state.udp.port)
        for key in (1,4,7,11,2):
            sender.sendto(wire[key],address)
        deadline=monotonic()+2
        while not app.state.udp.snapshot().get("cars") and monotonic()<deadline:
            sleep(.01)
        raw=app.state.udp.snapshot()
        f=live_frame(raw)
        assert f["boxNowPosition"]==2 and f["gameRejoin"]==1
        altered=live_frame(dict(raw,gamePitWindow=(7,7),gameRejoin=2))
        assert altered["forecast"]==f["forecast"]
        for slot in (0,1):
            wire[2][29+slot*57+33]=8
        struct.pack_into("<I",wire[2],23,11)
        sender.sendto(wire[2],address)
        while app.state.udp.snapshot()["cars"][0]["lap"] != 8 and monotonic()<deadline:
            sleep(.01)
        raw=app.state.udp.snapshot()
        assert raw["gameRejoin"]==1 and raw["boxNowPosition"]==2

def test_wear_risk_distinguishes_physical_wear_from_remaining_life():
    from live_timing import annotate_wear
    car = {"lap": 1, "compound": 16, "wheelWear": [4,5,3,2],
           "tyreSets": [(16,4,True,8,0,True), (17,10,True,6,0,False)]}
    plan = {"stops":[{"lap":10,"tyre":"M"}],
            "tyreIssues":[(9,9,"S","life"),(16,17,"M","life")]}
    annotate_wear(plan, car, {"S":{"wearPct":3.5}})
    assert plan["wearRisk"] == {9:{"wearPct":36.5,"excessPct":12.5},16:{"wearPct":None,"excessPct":33.3}}
