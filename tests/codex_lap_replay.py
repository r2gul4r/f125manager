"""Offline SDK-boundary test through recorded UDP, Rust, WebSocket and Chromium."""

import asyncio
import json
import os
import re
import socket
import sys
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import patch

import uvicorn
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f125_core
import server
from live_timing import live_frame
from wheel_input import WheelInput

RECORDING = "1794738164870921-629b389d612e65cc"
PICKS = {
    key: {"lap": lap, "tyre": "H", "reason": "Offline persistence check"}
    for key, lap in zip("ABC", (12, 12, 13))
}


def check_retained_preview(browser, url, frame):
    # Reproduce the screenshot with a past, unserved L7 soft in the committed plan.
    hard = {"lap":12, "tyre":"H"}
    previous = {**frame["forecast"], "lap":9}
    snapshot = {**frame, "plan":{"start":"M", "stops":[{"lap":7,"tyre":"S"},hard]},
                "forecast":None, "previousPlans":previous}
    page = browser.new_page()
    sockets = []

    def connect(ws):
        sockets.append(ws)
        ws.send(json.dumps(snapshot))

    page.route_web_socket("**/ws/demo", connect)
    page.goto(url+"?source=demo")
    page.get_by_role("button", name="My Race", exact=True).click()
    row = page.get_by_role("row").filter(has=page.get_by_role("button",name="Plan A · Balanced"))
    bar = page.get_by_label("Plan A preview").locator(".stint-bar")
    expect(row.locator(".stop-sequence")).to_contain_text("1 stop")
    expect(bar.locator("small")).to_have_text(["9–11","12–27"])
    assert [b.get_attribute("data-compound") for b in bar.locator("> span").all()] == ["M","H"]
    # Replace the retained forecast while the same accordion stays open.
    updated = {**previous["plans"][0], "stops":[{"lap":10,"tyre":"S"},hard]}
    forecast = {**previous, "plans":[updated,*previous["plans"][1:]]}
    sockets[-1].send(json.dumps({**snapshot,"forecast":forecast,"previousPlans":None}))
    expect(row.locator(".stop-sequence")).to_contain_text("2 stops")
    expect(bar.locator("small")).to_have_text(["9–9","10–11","12–27"])
    page.close()


def check(root, output, expiry=False):
    calls = []
    picks = {**PICKS, "B": {**PICKS["B"], "lap": 10}} if expiry else PICKS
    release = threading.Event()

    class LocalSdk:
        id = "offline-lap-retention"

        def __init__(self, config):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def thread_start(self, **options):
            return self

        async def thread_resume(self, thread_id, **options):
            assert thread_id == self.id
            return self

        async def run(self, facts, **options):
            data = json.loads(facts)
            targets = data["requestedPlans"]
            assert options["output_schema"]["required"] == targets
            calls.append((data["lap"], "".join(targets)))
            if targets == list("ABC"):
                assert data["lap"] == 6
                return SimpleNamespace(error=None, final_response=json.dumps(picks))
            assert expiry and targets == ["B"] and data["lap"] == 11
            assert data["keepPlans"] == {key:picks[key] for key in "AC"}
            while not release.is_set():
                await asyncio.sleep(.05)
            return SimpleNamespace(error=None, final_response=json.dumps({"B":{**picks["B"], "lap":11}}))

    with TemporaryDirectory() as scratch, socket.socket() as listener:
        env = {
            "F125_UDP_PORT": "0",
            "F125_RECORDING_DIR": scratch,
            "F125_PRACTICE_SAVE_DIR": str(Path(scratch) / "absent"),
            "LOCALAPPDATA": scratch,
        }
        listener.bind(("127.0.0.1", 0))
        application = uvicorn.Server(uvicorn.Config(server.app, log_level="warning"))
        with (
            patch.dict(os.environ, env),
            patch.object(WheelInput, "add", lambda *args: None),
            patch("gp_advisor.AsyncCodex", LocalSdk),
        ):
            worker = threading.Thread(
                target=lambda: asyncio.run(application.serve(sockets=[listener]))
            )
            worker.start()
            try:
                deadline = monotonic() + 15
                while not application.started and monotonic() < deadline:
                    sleep(0.05)
                assert application.started
                server.app.state.record_dir = root
                records = []
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(channel="chrome", headless=True)
                    page = browser.new_page(viewport={"width": 1920, "height": 1080})
                    messages, errors, sent = [], [], []
                    page.on("websocket", lambda ws: ws.on("framesent", lambda data: sent.append(json.loads(data))))
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on(
                        "websocket",
                        lambda ws: ws.on(
                            "framereceived",
                            lambda payload: messages.append(json.loads(payload)),
                        ),
                    )
                    page.goto(
                        f"http://127.0.0.1:{listener.getsockname()[1]}/?replay={RECORDING}"
                    )
                    slider = page.get_by_label("Replay time")
                    expect(slider).to_be_visible()
                    page.get_by_role("button", name="My Race", exact=True).click()

                    def seek(ms):
                        page.wait_for_function(
                            """ms => Number(document.querySelector('[aria-label="Replay time"]')?.max) >= ms""",
                            arg=ms,
                        )
                        slider.evaluate(
                            """(el,ms)=>{
                            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(ms));
                            el.dispatchEvent(new Event('input',{bubbles:true}));
                        }""",
                            ms,
                        )
                        try:
                            expect(slider).to_have_value(str(ms), timeout=15000)
                        except AssertionError:
                            print("Replay status:", messages[-1].get("error"), page.locator("body").inner_text()[:350], errors, flush=True)
                            raise
                        for _ in range(100):
                            if (
                                messages
                                and messages[-1].get("playback", {}).get("ms") == ms
                            ):
                                return messages[-1]["frame"]
                            page.wait_for_timeout(50)
                        raise AssertionError(
                            "Replay clock did not reach requested sample"
                        )

                    if not expiry:
                        for ms, reason in [(122000, "Waiting for timing gaps"), (1351000, "Waiting for tyre history")]:
                            pending = seek(ms)
                            assert not pending["forecast"] and not pending.get("previousPlans")
                            expect(page.locator(".plan-comparison h3")).to_contain_text(reason)
                        # Seeking directly into a gap outage must still give a read-only preview.
                        for ms in (796000, 728000, 747000):
                            frame = seek(ms)
                            assert not frame["forecast"] and frame["previousPlans"]["lap"] == frame["lap"]
                            expect(page.locator(".plan-comparison h3")).to_contain_text("Last forecast")
                            for key in "ABC":
                                choice = page.get_by_role("button", name=f"Plan {key} ·", exact=False)
                                choice.hover()
                                preview = page.get_by_label(f"Plan {key} preview")
                                stop = frame["previousPlans"]["plans"]["ABC".index(key)]["stops"][0]
                                offset = stop["lap"] - frame["previousPlans"]["lap"]
                                outlook = frame["previousPlans"]["tyreExits"][offset]
                                after = preview.get_by_role("table", name="After pit")
                                expect(after.locator("tbody td").nth(1)).to_have_text(f"P{outlook['position']}")
                                expect(after.locator(".rank-driver b")).to_have_text(
                                    [code for code in (outlook["before"], outlook["after"]) if code])
                                service = preview.get_by_role("table", name="Pit service comparison")
                                for idx, (rank, loss, _) in enumerate(frame["previousPlans"]["serviceRejoins"][offset]):
                                    expect(service.locator("tbody tr").nth(idx).locator("td")).to_have_text(
                                        [f"{loss/1000:.2f}s", f"P{rank}"])
                                expect(preview.locator(".cut-outcome strong")).to_have_text(
                                    [re.compile(r"^\d+%$"), re.compile(r"^\d+%$")])
                                choice.click()
                                expect(page.get_by_label("Selected strategy")).not_to_contain_text(f"Plan {key}")
                                percent = preview.locator(".cut-outcome").first
                                badge = percent.locator(".rank-driver").first.bounding_box()
                                value = percent.locator("strong").bounding_box()
                                assert value["y"] >= badge["y"] + badge["height"] - 1
                        old = seek(1076000)
                        new = seek(1085000)
                        assert old["session"] != new["session"]
                        assert {e["id"] for e in old["events"]} <= {e["id"] for e in new["events"]}
                        assert any(e["label"] == "플래시백" for e in new["events"])
                        lap12 = seek(1093000)
                        assert lap12["session"] == new["session"] and lap12["lap"] == 12
                        plans = lap12["forecast"]["plans"]
                        assert [p["id"] for p in plans] == list("ABC")
                        assert [p["stop"] for p in plans] == [
                            {"lap": n, "tyre": "H"} for n in (12, 12, 13)
                        ]
                        for key in "ABC":
                            choice = page.get_by_role("button", name=f"Plan {key} ·", exact=False)
                            expect(choice).to_be_enabled()
                            choice.hover()
                            table = page.get_by_label(f"Plan {key} preview").get_by_role("table", name="After pit")
                            expect(table.locator("tbody td").nth(1)).to_have_text("P1")
                        page.get_by_role("button", name="Plan A ·", exact=False).hover()
                        page.locator(".race-strategy").screenshot(path=str(output/"monza-1813-plans.png"))
                        page.get_by_role("button", name="Live Timing", exact=True).click()
                        event_frame = page.locator(".event-id .name-frame").first
                        expect(event_frame).to_have_css("border-top-width", "0px")
                        assert event_frame.evaluate("(e)=>getComputedStyle(e).paddingTop===getComputedStyle(e).paddingRight")
                        page.get_by_role("button", name="My Race", exact=True).click()
                        print("PASS Monza 12:08 / 13:16 A/B/C previews and flashback event history", flush=True)
                        for ms, key, expected in [
                            (1137000, "A", ["20.37s", "P1", "25.57s", "P2"]),
                            (2396000, "B", ["20.35s", "P2", "25.55s", "P2"]),
                            (1152000, "A", ["20.37s", "P1", "25.57s", "P2"]),
                        ]:
                            sample = seek(ms)
                            choice = page.get_by_role("button", name=f"Plan {key} ·", exact=False)
                            choice.hover()
                            preview = page.get_by_label(f"Plan {key} preview")
                            service = preview.get_by_role("table", name="Pit service comparison")
                            expect(service.locator("tbody td")).to_have_text(expected)
                            if ms == 1152000:
                                assert sample["lap"] == 13 and sample["forecast"] is None
                                assert [p["id"] for p in sample["previousPlans"]["plans"]] == list("ABC")
                                expect(page.locator(".plan-comparison h3")).to_contain_text("Before pit entry")
                                expect(service.locator("caption")).to_contain_text("L12")
                                choice.click()
                                expect(page.get_by_label("Selected strategy")).not_to_contain_text("Plan A")
                        exited = seek(1166042)
                        assert exited["forecast"]["plans"][0]["stops"] == [] and not exited.get("previousPlans")
                        assert exited["cars"][exited["player"]]["tyre"] == "H"
                        print("PASS Monza pit service at 18:57 / 39:56 and read-only pit plans at 19:12", flush=True)
                        # Drag backward through many input events while frames arrive.
                        # A single release must restore the final cursor and recorded lap.
                        for playing in (False, True):
                            seek(2400000)
                            if playing:
                                page.get_by_role("button", name="Play",exact=True).click()
                                expect(page.get_by_label("Playback speed")).to_have_value("1")
                            bounds = slider.bounding_box()
                            x,y,w = bounds["x"],bounds["y"]+bounds["height"]/2,bounds["width"]
                            first_message = len(sent)
                            page.mouse.move(x+w*.94,y)
                            page.mouse.down()
                            page.mouse.move(x+w*.35,y,steps=18)
                            dest = int(slider.input_value())
                            page.wait_for_timeout(250)
                            expect(slider).to_have_value(str(dest))
                            assert not any("ms" in cmd for cmd in sent[first_message:])
                            page.mouse.up()
                            for _ in range(200):
                                if messages[-1].get("playback",{}).get("ms")==dest:
                                    break
                                page.wait_for_timeout(25)
                            assert messages[-1]["playback"]["ms"] == dest
                            assert [p["ms"] for p in sent[first_message:] if "ms" in p] == [dest]
                            expect(page.get_by_label("Playback speed")).to_have_value("0")
                            assert 820000 < dest < 920000
                            reference = f125_core.Replay(root / RECORDING)
                            expected = live_frame(reference.advance(dest), pit_ms=reference.pit_loss_ms)
                            restored = messages[-1]["frame"]
                            assert restored["lap"] == expected["lap"]
                            assert restored["pitComparisons"] == json.loads(json.dumps(expected["pitComparisons"]))
                            expect(page.locator(".race-caption")).to_contain_text(f"Current lap L{expected['lap']}")
                            expect(slider).to_have_value(str(dest))
                        print("PASS Monza backward pointer drag, playing and paused",flush=True)
                        rows = page.locator(".plan-table tr:has(.plan-choice)")
                        seek(661000)
                        rows.first.get_by_role("button").focus()
                        risk = page.get_by_label("Plan A preview").get_by_role("table", name="Risk details")
                        expect(risk.get_by_role("columnheader")).to_have_text(["Pit entry → exit","Traffic ahead ≤3s","Undercut by","Overcut by"])
                        cells = risk.get_by_role("cell")
                        expect(cells.nth(0)).to_have_text("P2 → P12 10 lost")
                        expect(cells.nth(1).locator(".name-frame b")).to_have_text(["HAD"])
                        expect(cells.nth(1).locator(".traffic-car strong")).to_have_text(["+0.385s"])
                        for cell in (cells.nth(2),cells.nth(3)):
                            expect(cell.locator(".name-frame b")).to_have_text(["COR","PIA"])
                            expect(cell.locator("strong")).to_have_text("0%")
                            expect(cell).not_to_contain_text("0/5")
                        risk.screenshot(path=str(output/"monza-risk-1101.png"))
                        rows.nth(1).get_by_role("button").focus()
                        risk_b = page.get_by_label("Plan B preview").get_by_role("table", name="Risk details")
                        traffic = risk_b.get_by_role("cell").nth(1)
                        expect(traffic.locator(".traffic-car:visible .name-frame b")).to_have_text(["PER","ALO"])
                        more = traffic.get_by_role("button")
                        expect(more).to_have_text("+4")
                        first, second = [car.bounding_box() for car in traffic.locator(".traffic-car").all()]
                        toggle = more.bounding_box()
                        assert first["y"] + first["height"] <= second["y"] and abs(first["x"]-second["x"]) < 1
                        assert toggle["x"] >= second["x"] + second["width"]
                        assert abs(toggle["y"]+toggle["height"]/2-second["y"]-second["height"]/2) < 1
                        risk_b.screenshot(path=str(output/"monza-risk-1101-B.png"))
                        more.click()
                        expect(traffic.locator(".traffic-car:visible .name-frame b")).to_have_text(["PER","ALO","BOR","VER","STR","OCO"])
                        expect(traffic.locator(".traffic-car:visible strong")).to_have_text(["+0.279s","+0.695s","+1.878s","+2.295s","+2.562s","+2.829s"])
                        more.click()
                        seek(850400)
                        seek(850500)
                        expected_exits = {
                            "A": ("P3",["ALB","HAD"],["+4.947s","−4.073s"],["closing","opening"]),
                            "B": ("P4",["HAD","LIN"],["+0.340s","−1.193s"],["closing","opening"]),
                            "C": ("P3",["ALB","HAD"],["+4.381s","−4.928s"],["closing","opening"]),
                        }
                        for key in "ABCA":
                            button = rows.nth("ABC".index(key)).get_by_role("button")
                            button.hover()
                            panel = page.get_by_label(f"Plan {key} preview")
                            table = panel.get_by_role("table",name="After pit")
                            rank, drivers, gaps, trends = expected_exits[key]
                            expect(table.locator("tbody td").nth(1)).to_have_text(rank)
                            expect(table.locator(".rank-driver b")).to_have_text(drivers)
                            selected_gaps = page.get_by_label("Selected strategy").locator(".exit-neighbour strong")
                            numbers = table.locator(".exit-neighbour strong")
                            expect(numbers).to_have_text(gaps)
                            for number, trend in zip(numbers.all(),trends):
                                expect(number).to_have_attribute("data-trend",trend)
                                if trend!="steady":
                                    color = {"opening":"rgb(255, 218, 89)","closing":"rgb(113, 223, 139)"}[trend]
                                    expect(number).to_have_css("color",color)
                            metrics = panel.get_by_role("table", name="Risk details").get_by_role("cell")
                            expect(metrics.nth(2).locator("strong")).to_have_text("0%")
                            expect(metrics.nth(3).locator("strong")).to_have_text("0%")
                            for pair in page.locator(".exit-neighbour").all():
                                badge = pair.locator(".rank-driver").bounding_box()
                                gap = pair.locator("strong").bounding_box()
                                assert badge["x"]+badge["width"] <= gap["x"]
                                assert abs(badge["y"]+badge["height"]/2-gap["y"]-gap["height"]/2) < 1
                            for row in [page.locator(".plan-table > thead > tr"), *rows.all()]:
                                for col in row.locator(":scope > :is(th,td):not(:first-child)").all():
                                    expect(col).to_have_css("text-align","center")
                            risk_table = panel.get_by_role("table", name="Risk details")
                            for cells in (risk_table.get_by_role("columnheader"),metrics):
                                expect(cells).to_have_count(4)
                                for n, cell in enumerate(cells.all()):
                                    expect(cell).to_have_css("text-align","center")
                                    if n: expect(cell).to_have_css("border-inline-start-width","1px")
                            panel.screenshot(path=str(output/f"monza-after-pit-{key}.png"))
                            if key=="B":
                                page.screenshot(path=str(output/"monza-A-hover-B.png"))
                            button.click()
                            expect(page.get_by_label("Selected strategy")).to_contain_text("Plan "+key)
                            expect(table).to_be_visible()
                            expect(page.get_by_text("재생 계획 적용됨",exact=True)).to_have_count(0)
                            expect(table.locator("tbody td").nth(1)).to_have_text(rank)
                            expect(selected_gaps).to_have_text(gaps)
                            if key=="A":
                                page.screenshot(path=str(output/"monza-A-selected.png"))
                        seek(302000)
                        for key, under in (("B","0%"),("C","60%"),("A","0%")):
                            rows.nth("ABC".index(key)).get_by_role("button").focus()
                            metrics = page.get_by_label(f"Plan {key} preview").get_by_role("table", name="Risk details").get_by_role("cell")
                            expect(metrics.nth(2).locator("strong")).to_have_text(under)
                            expect(metrics.nth(3).locator("strong")).to_have_text("0%")
                        print("PASS Monza L9 A/B/C/A ranks, gap colours, losses; L3 undercut 0/60/0%",flush=True)
                        frame = seek(566000)
                        assert frame["lap"] == 6
                        rows = page.locator(".plan-table tr:has(.plan-choice)")
                        labels = rows.locator(".stop-sequence")
                        expect(labels).to_have_count(3)
                        schedules = labels.all_text_contents()
                        wire = {p["id"]:p["stops"] for p in frame["forecast"]["plans"]}
                        assert len(wire["A"])==1 and len(wire["B"])==2, wire
                        for key in "ABCA":
                            rows.nth("ABC".index(key)).get_by_role("button").click()
                            expect(page.get_by_label("Selected strategy")).to_contain_text("Plan "+key)
                            assert labels.all_text_contents()==schedules, (key,schedules,labels.all_text_contents())
                            current = messages[-1]["frame"]
                            assert current["plan"]["stops"]==wire[key]
                            assert {p["id"]:p["stops"] for p in current["forecast"]["plans"]}==wire
                        page.screenshot(path=str(output/"monza-my-race-full-hd.png"))
                        print("PASS Monza 09:26 paused A/B/C/A:", schedules)
                    initial = seek(600000)
                    original = initial["forecast"]["plans"][1]["stop"]
                    assert original != {"lap": picks["B"]["lap"], "tyre": "H"}
                    page.get_by_role(
                        "button", name="Request Codex plan", exact=True
                    ).click()
                    rows = page.locator(".plan-table tr:has(.plan-choice)")
                    expect(rows.nth(1).locator(".stop-sequence")).to_contain_text(f"L{picks['B']['lap']}")
                    page.get_by_role("button", name="Plan A · Balanced").click()
                    selected = page.get_by_label("Selected strategy")
                    expect(selected).to_contain_text("Plan A")
                    first_schedule = None
                    reply_id = None
                    for ms in (600000, 700000, 850000, 855000, 860000, 938795, 960000):
                        if ms == 960000:
                            seek(953000)
                            playback = page.get_by_label("Playback speed")
                            start = len(messages)
                            playback.select_option("1")
                            expect(page.locator(".plan-comparison h3")).to_contain_text("L11", timeout=10000)
                            playback.select_option("0")
                            if expiry:
                                b = rows.nth(1)
                                expect(b.get_by_role("button")).to_be_disabled()
                                expect(b.locator(".expired-mark")).to_have_text("×")
                                expect(b.locator(".expired-mark")).to_have_css("color", "rgb(255, 83, 83)")
                                expect(b.locator(".stop-sequence")).to_contain_text("L10")
                                for i in (0,2):
                                    expect(rows.nth(i).get_by_role("button")).to_be_enabled()
                                expect(selected).to_contain_text("Plan A")
                                page.locator(".plan-comparison").screenshot(path=str(output/"monza-B-expired.png"))
                                release.set()
                                expect(b.get_by_role("button")).to_be_enabled()
                                expect(b.locator(".expired-mark")).to_have_count(0)
                                expect(b.locator(".stop-sequence")).to_contain_text("L11")
                                expect(selected).to_contain_text("Plan A")
                                after = messages[-1]["frame"]["forecast"]["plans"]
                                assert [after[i]["stops"] for i in (0,2)] == [first_schedule[i] for i in (0,2)]
                                assert after[1]["stop"] == {"lap":11, "tyre":"H"}
                                assert calls == [(6,"ABC"), (11,"B")] and not errors
                                page.locator(".plan-comparison").screenshot(path=str(output/"monza-B-renewed.png"))
                                print("PASS Monza L10 -> L11: B expired, disabled, red X; only B requested and replaced. A/C schedules and selection preserved.", calls)
                                browser.close()
                                return
                            crossing = [m["frame"] for m in messages[start:] if m.get("frame")]
                            assert {f["lap"] for f in crossing} == {10, 11}
                            for f in crossing:
                                published = f["forecast"] or f["previousPlans"]
                                assert [p["stops"] for p in published["plans"]] == first_schedule
                            expect(selected).to_contain_text("Plan A")
                        frame = seek(ms)
                        forecast = frame["forecast"]
                        schedules = [p["stops"] for p in forecast["plans"]]
                        first_schedule = first_schedule or schedules
                        assert schedules == first_schedule, (
                            ms,
                            schedules,
                            first_schedule,
                        )
                        reply_id = reply_id or frame["advisor"]["id"]
                        assert frame["advisor"]["id"] == reply_id
                        assert all(p.get("codexReason") for p in forecast["plans"])
                        for i, plan in enumerate(forecast["plans"]):
                            assert plan["stop"] == {
                                "lap": picks[plan["id"]]["lap"],
                                "tyre": "H",
                            }
                            expect(
                                rows.nth(i).locator(".stop-sequence")
                            ).to_contain_text("L" + str(plan["stop"]["lap"]))
                            expect(
                                rows.nth(i).locator(".stop-sequence .tyre-badge").first
                            ).to_have_attribute("data-compound", "H")
                        exit_estimate = forecast["tyreExits"][12 - frame["lap"]]
                        preview = page.get_by_label("Plan A preview")
                        service = preview.get_by_role("table", name="Pit service comparison")
                        expect(service.get_by_role("columnheader")).to_have_text(["Service","Est. pit loss","Rejoin"])
                        player = frame["cars"][frame["player"]]
                        upcoming = schedules[0]
                        starts = [(frame["lap"], player["tyre"])] + [(s["lap"], s["tyre"]) for s in upcoming]
                        ends = [lap-1 for lap, _ in starts[1:]] + [frame["totalLaps"]]
                        expected = [(tyre, f"{lap}–{end}") for (lap,tyre),end in zip(starts,ends) if lap<=end]
                        bars = preview.locator(".stint-bar > span")
                        expect(bars.locator("small")).to_have_text([label for _,label in expected])
                        assert [bar.get_attribute("data-compound") for bar in bars.all()] == [tyre for tyre,_ in expected]
                        for i, label in enumerate(("Tyres only", "Tyres + front wing")):
                            cells = service.get_by_role("row", name=label).get_by_role("cell")
                            position, loss, _ = forecast["serviceRejoins"][12 - frame["lap"]][i]
                            expect(cells).to_have_text([f"{loss/1000:.2f}s",f"P{position}"])
                        after = preview.get_by_role("table", name="After pit")
                        expect(after.locator("tbody td").nth(1)).to_have_text("P"+str(exit_estimate["position"]))
                        expect(service.locator("caption")).to_have_text("Pit service Pit on L12")
                        expect(page.locator(".race-caption")).to_contain_text(f"Current lap L{frame['lap']}")
                        expect(preview.get_by_label("Pit exit forecast")).to_have_count(0)
                        expect(selected.locator(".rejoin-summary b").first).to_have_text("P"+str(exit_estimate["position"]))
                        assert selected.locator(".rejoin-summary b").evaluate("el => parseFloat(getComputedStyle(el).fontSize)") >= 24
                        for label, key, gap_key, sign in (("Ahead","before","aheadGapMs","+"),("Behind","after","behindGapMs","−")):
                            rival = selected.get_by_label(label, exact=True)
                            if exit_estimate[key]:
                                expect(rival.locator(".name-frame b")).to_have_text(exit_estimate[key])
                            else:
                                expect(rival).to_contain_text("—")
                            gap = exit_estimate[gap_key]
                            if gap is None:
                                expect(rival.locator("strong")).to_have_count(0)
                            else:
                                expect(rival.locator("strong")).to_have_text(f"{sign}{gap / 1000:.3f}s")
                        expect(selected).to_contain_text("L12")
                        records.append(
                            {
                                "ms": ms,
                                "lap": frame["lap"],
                                "plans": schedules,
                                "replyId": reply_id,
                                "rejoin": exit_estimate,
                                "ui": selected.inner_text(),
                            }
                        )
                        if not expiry and ms in (850000, 855000):
                            if ms == 850000:
                                check_retained_preview(browser, page.url.split("?")[0], frame)
                                rows.nth(1).get_by_role("button").focus()
                                comparison = page.get_by_label("Plan B preview")
                                service = comparison.get_by_role("table",name="Pit service comparison")
                                after = comparison.get_by_role("table",name="After pit")
                                viewport = page.viewport_size
                                for width, height in ((1920,1080), (1280,720), (447,883)):
                                    page.set_viewport_size({"width":width, "height":height})
                                    for table in (service,after):
                                        expect(table.locator("colgroup + colgroup").first).to_have_css("border-inline-start-width","2px")
                                        assert table.locator("caption, th, td").evaluate_all(
                                            "cells => cells.every(c => getComputedStyle(c).textAlign === 'center')"
                                        )
                                        bounds = table.bounding_box()
                                        assert bounds["x"] >= 0 and bounds["x"]+bounds["width"] <= width, (width, bounds)
                                    left, right = service.bounding_box(), after.bounding_box()
                                    divider = comparison.locator(".pit-outlooks").evaluate("""el => {
                                        const style = getComputedStyle(el, '::before')
                                        return [parseFloat(style.width),parseFloat(style.height)]
                                    }""")
                                    if width==1920:
                                        assert divider[0] == 2 and divider[1] >= left["height"]-1, divider
                                        assert left["x"]+left["width"]<=right["x"] and abs(left["y"]-right["y"])<1, (left,right)
                                        assert abs(left["height"]-right["height"])<1, (left,right)
                                        assert abs(left["width"]/(left["width"]+right["width"])-0.4)<0.01, (left,right)
                                    if width==447:
                                        assert divider[1] == 2 and divider[0] >= left["width"]-1, divider
                                        assert left["y"]+left["height"]<=right["y"], (left,right)
                                page.set_viewport_size(viewport)
                                for i, key in enumerate("BC", start=1):
                                    rows.nth(i).get_by_role("button").focus()
                                    panel = page.get_by_label(f"Plan {key} preview")
                                    target = picks[key]["lap"]
                                    table = panel.get_by_role("table",name="Pit service comparison")
                                    expect(table.locator("caption")).to_contain_text(f"L{target}")
                                    rank = forecast["serviceRejoins"][target - frame["lap"]][0][0]
                                    expect(table.locator("tbody tr").first.locator("td").last).to_have_text(f"P{rank}")
                                rows.first.get_by_role("button").focus()
                            preview.screenshot(path=str(output / f"monza-plan-rejoin-{ms}.png"))
                            page.screenshot(
                                path=str(output / f"codex-retained-{ms}.png")
                            )
                    assert [row["lap"] for row in records] == [6, 7, 9, 9, 9, 10, 11]
                    assert records[1]["rejoin"]["trafficAhead"] == [["ANT", 2302], ["NOR", 2309]]
                    assert records[2]["rejoin"]["before"] == "ALB" and records[2]["rejoin"]["trafficAhead"] == []
                    assert records[3]["rejoin"]["before"] == "COL"
                    assert records[3]["rejoin"]["trafficAhead"] == []
                    assert len({row["rejoin"]["position"] for row in records}) >= 4
                    assert calls == [(6,"ABC")] and not errors
                    # Every preview keeps its own exit table after committing any plan.
                    for committed in "BCA":
                        rows.nth("ABC".index(committed)).get_by_role("button").click()
                        expect(selected).to_contain_text("Plan "+committed)
                        for i, key in enumerate("ABC"):
                            rows.nth(i).get_by_role("button").hover()
                            panel = page.get_by_label(f"Plan {key} preview")
                            expect(panel).to_be_visible()
                            expect(panel.get_by_role("table",name="After pit")).to_be_visible()
                    output.joinpath("codex-lap-retention.json").write_text(
                        json.dumps(
                            {
                                "recording": RECORDING,
                                "sdk": "local deterministic test response",
                                "requests": calls,
                                "observations": records,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    browser.close()
                print(
                    json.dumps(
                        [{"lap": r["lap"], **r["rejoin"]} for r in records],
                        ensure_ascii=False,
                    )
                )
                print(
                    "PASS: one proposal, A/B/C schedules preserved L6–L11; live rank and traffic verified in DOM."
                )
            finally:
                application.should_exit = True
                worker.join(10)
                assert not worker.is_alive()


if __name__ == "__main__":
    folder = Path("output/playwright")
    folder.mkdir(parents=True, exist_ok=True)
    check(Path(sys.argv[1]).resolve(), folder, "--expiry" in sys.argv)
