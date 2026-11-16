"""Windows Chrome + SDL virtual wheel. Run from repo root after the web build."""
import asyncio
import ctypes as ct
import json
import os
import socket
import struct
import sys
import threading
from pathlib import Path
from time import monotonic, sleep

import uvicorn
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from wheel_input import pygame
from test_live_udp import packets


class VirtualWheel:
    def __init__(self):
        self.sdl = ct.CDLL(str(Path(pygame.__file__).with_name("SDL2.dll")))
        self.sdl.SDL_JoystickOpen.restype = ct.c_void_p
        self.sdl.SDL_JoystickSetVirtualButton.argtypes = [ct.c_void_p, ct.c_int, ct.c_uint8]
        self.sdl.SDL_JoystickSetVirtualHat.argtypes = [ct.c_void_p, ct.c_int, ct.c_uint8]
        self.sdl.SDL_JoystickClose.argtypes = [ct.c_void_p]
        self.index = self.sdl.SDL_JoystickAttachVirtual(2, 0, 64, 1)
        assert self.index >= 0
        self.handle = self.sdl.SDL_JoystickOpen(self.index)
        assert self.handle

    def press(self, control, value, held=.12):
        setter, index = (self.sdl.SDL_JoystickSetVirtualHat, 0) if control == "hat" else (
            self.sdl.SDL_JoystickSetVirtualButton, control-1)
        assert setter(self.handle, index, value) == 0
        sleep(held)
        assert setter(self.handle, index, 0) == 0
        sleep(.12)

    def close(self):
        self.sdl.SDL_JoystickClose(self.handle)
        self.sdl.SDL_JoystickDetachVirtual(self.index)


def check_tyre_badges(container):
    badges = container.locator(".tyre-badge[data-compound]")
    assert badges.count() > 0
    errors = badges.evaluate_all("""badges => badges.flatMap(badge => {
        const glyph = badge.querySelector('.tyre-glyph'), ring = badge.getBoundingClientRect();
        const letter = glyph.getBoundingClientRect(), css = getComputedStyle(badge);
        const colors = {H:'rgb(255, 255, 255)', M:'rgb(246, 216, 76)', S:'rgb(255, 80, 89)',
                        I:'rgb(87, 203, 118)', W:'rgb(71, 179, 239)'};
        const color = colors[badge.dataset.compound];
        return css.borderTopColor === color && getComputedStyle(glyph).fill === color &&
               Math.abs(ring.width-ring.height) < .1 && letter.width > 0 && letter.width < ring.width*.85
               ? [] : [badge.outerHTML];
    })""")
    assert not errors, errors[:2]


def check_layout(page, width, height):
    assert page.evaluate("""() => document.documentElement.scrollWidth <= innerWidth &&
        document.documentElement.scrollHeight <= innerHeight""")
    for selector in ('.battle-stats','.neighbors table','.pace','.weather-call','.pit-estimates','.plan-actions','.inline-confirm'):
        if not page.locator(selector).count() and selector in ('.weather-call','.pit-estimates','.plan-actions','.inline-confirm'):
            continue
        rect = page.locator(selector).bounding_box()
        assert 0 <= rect["x"] and rect["x"]+rect["width"] <= width+1, (selector,rect)
        assert 0 <= rect["y"] and rect["y"]+rect["height"] <= height+1, (selector,rect)
    expect(page.locator(".my-race footer")).to_have_count(0)


def check_wheel_analysis(analysis, wheel):
    def down_to(control):
        wheel.press("hat",4)
        expect(control).to_be_focused()

    gp = analysis.get_by_role("combobox",name="Grand Prix",exact=True)
    down_to(gp)
    wheel.press("hat",2)
    expect(gp).to_have_value("Japan")
    wheel.press("hat",2)
    expect(gp).to_have_value("Bahrain")
    down_to(analysis.get_by_label("Session type"))
    session = analysis.get_by_label("Session",exact=True)
    down_to(session)
    wheel.press("hat",2)
    expect(session.locator("option:checked")).to_have_text("Bahrain · Race")
    view = analysis.get_by_label("View",exact=True)
    down_to(view)
    for label, lap in (("Lap A","18"),("Lap B","19")):
        picker = analysis.get_by_label(label,exact=True)
        down_to(picker)
        wheel.press("hat",2)
        expect(picker).to_have_value(lap)
    expect(analysis.get_by_role("cell",name="A · L18",exact=True)).to_be_visible()
    expect(analysis.get_by_role("cell",name="B · L19",exact=True)).to_be_visible()
    down_to(analysis.get_by_label("Channel"))
    wheel.press("hat",2)
    expect(analysis.get_by_role("img",name="Throttle comparison by lap distance")).to_be_visible()
    distance = analysis.get_by_role("slider")
    down_to(distance)
    wheel.press("hat",2)
    expect(analysis.get_by_text("Distance · 492 m")).to_be_visible()
    down_to(analysis.locator("summary"))
    wheel.press(2,1)
    expect(analysis.get_by_role("columnheader",name="S1 (s)",exact=True)).to_be_visible()
    for _ in range(5):
        wheel.press("hat",1)
    expect(view).to_be_focused()
    wheel.press("hat",2)
    stint = analysis.get_by_role("combobox",name="Stint")
    down_to(stint)
    wheel.press("hat",8)
    expect(stint.locator("option:checked")).to_have_text("Stint 2")
    heading = analysis.get_by_role("heading",name="Lap replay · L20")
    expect(heading).to_be_visible()
    down_to(analysis.get_by_role("button",name="Play",exact=True))
    wheel.press(2,1)
    expect(analysis.get_by_role("button",name="Pause")).to_be_focused()
    expect(analysis.get_by_role("heading",name="Lap replay · L21")).to_be_visible()
    wheel.press(2,1)
    expect(analysis.get_by_role("button",name="Play",exact=True)).to_be_focused()
    scrubber = analysis.get_by_label("Replay lap")
    down_to(scrubber)
    wheel.press("hat",8)
    expect(heading).to_be_visible()
    wheel.press("hat",2)
    expect(analysis.get_by_role("heading",name="Lap replay · L21")).to_be_visible()
    down_to(analysis.get_by_role("button",name="L20",exact=True))
    wheel.press(2,1)
    expect(heading).to_be_visible()


def check_wheel_recommended_plan(page, wheel, requests):
    recommended = page.locator(".plan-table tr:has(.plan-rec)")
    comparison = page.get_by_role("region",name="Strategy comparison")
    committed = page.locator(".weather-call")
    original = committed.text_content()
    initial_count = len(requests)
    expect(recommended.get_by_role("button")).to_have_accessible_name("Plan B · Undercut")
    wheel.press(3,1)  # Return to Plan A.
    for plan_id in ("A","B","C"):
        row = comparison.get_by_role("button",name=f"Plan {plan_id} ·")
        expect(row).to_have_attribute("aria-pressed","true")
        expect(comparison.get_by_label(f"Plan {plan_id} preview")).to_be_visible()
        if plan_id!="C":
            wheel.press("hat",4)
    wheel.press("hat",1)  # Back to the recommended Plan B.
    assert len(requests)==initial_count
    expect(committed).to_have_text(original)
    expect(comparison.get_by_label("Plan B preview")).to_be_visible()
    expected = page.locator(".plan-table tr[data-active=true] .schedule-stop .tyre-badge").first.get_attribute("data-compound")
    wheel.press(2,1)
    expect(committed.locator(".tyre-badge").first).to_have_attribute("data-compound",expected)
    assert len(requests)==initial_count+1


def check_live_sessions(browser, url):
    page = browser.new_page()
    advisor_requests = []
    def intercept_advisor(ws):
        upstream = ws.connect_to_server()
        def on_command(message):
            cmd = json.loads(message)
            if cmd.get("type") == "askCodex":
                advisor_requests.append(cmd)
            else:
                upstream.send(message)
        ws.on_message(on_command)
    page.route_web_socket("**/ws/live", intercept_advisor)
    page.goto(url)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        address = ("127.0.0.1", server.app.state.udp.port)
        for session_id, name in ((1, "FP1"), (5, "Q1"), (15, "Race")):
            wire = packets(2026, uid=session_id)
            wire[1][35:37] = bytes((session_id, 3))  # Bahrain
            struct.pack_into("<H", wire[1], 38, 1234)
            for packet_id, payload in wire.items():
                if packet_id != 0:  # No motion samples or prior browser trail.
                    sender.sendto(payload, address)
            expect(page.locator(".session b")).to_have_text(name)
            if name == "FP1":
                circuit = page.locator('.circuit[data-circuit="bahrain"]')
                art = circuit.locator(".circuit-art")
                expect(art).to_have_attribute("href", "/circuits/timing/bahrain.webp")
                assert art.evaluate("""async el => {
                    const img = new Image(); img.src = el.getAttribute('href'); await img.decode();
                    const canvas = document.createElement('canvas');
                    canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
                    const ctx = canvas.getContext('2d'); ctx.drawImage(img,0,0);
                    const pixel = (x,y) => [...ctx.getImageData(x,y,1,1).data];
                    // Cross the main straight at right angles. Both white rims must
                    // cover three pixels including the antialiasing at this location.
                    const rims = Array.from({length:41}, (_,i)=>633+i).filter(y=>{
                        const [r,g,b,a]=pixel(472,y);
                        return Math.min(r,g,b)>135 && a>150;
                    });
                    return canvas.width === 1252 && canvas.height === 704 &&
                        rims.join() === '635,636,637,669,670,671' &&
                        pixel(0,0)[3] === 0 && pixel(472,653)[0] > 190 &&
                        pixel(472,653)[2] > 70 && pixel(472,653)[1] < 55;
                }""")
                expect(circuit.locator("[data-marker]")).to_have_count(2)
                # Two yellow posts on opposite sides of the same timing sector.
                # The last post also wraps across the start/finish line.
                session_packet=wire[1]
                posts=[(.03125,0),(.125,3),(.15625,0),(.21875,3),(.25,1),(.96875,3)]
                session_packet[47]=len(posts)
                for i,(start,flag) in enumerate(posts):
                    struct.pack_into("<fb",session_packet,48+5*i,start,flag)
                struct.pack_into("<I",session_packet,23,11)
                sender.sendto(session_packet,address)
                overlay=circuit.locator("[data-yellow-intervals]")
                expect(overlay).to_have_attribute("data-yellow-intervals","[[0.125,0.15625],[0.21875,0.25],[0.96875,1],[0,0.03125]]")
                path=json.loads((Path(__file__).resolve().parents[1]/"assets/boxbox/image-paths.json").read_text())["bahrain"]
                # T3–4 and T13–14 pass under sector labels in the original diagram.
                # Check both the registered car line and the actual flag mask.
                for first, last in [(88, 134), (375, 435)]:
                    x, y = path[first]
                    dx, dy = path[last][0] - x, path[last][1] - y
                    length = (dx**2 + dy**2)**0.5
                    normal = [-dy / length, dx / length]
                    straight = path[first + 3:last - 2]
                    assert max(abs((px-x)*normal[0] + (py-y)*normal[1]) for px, py in straight) < .1
                    assert art.evaluate("""async (_, [points, [nx, ny]]) => {
                        const img = new Image(); img.src = '/circuits/flag-edges/bahrain.png';
                        await img.decode();
                        const ctx = document.createElement('canvas').getContext('2d');
                        ctx.canvas.width = img.width; ctx.canvas.height = img.height;
                        ctx.drawImage(img, 0, 0);
                        const pixels = ctx.getImageData(0, 0, img.width, img.height).data;
                        return points.every(([x,y]) => {
                            const alpha = offset => pixels[4*(Math.round(y+ny*offset)*img.width
                                + Math.round(x+nx*offset))+3];
                            return [-17,17].every(d => alpha(d)>80)
                                && [-21,-13,13,21].every(d => alpha(d)<40);
                        });
                    }""", [straight, normal])
                inside=[.14,.235,.99,.015]
                outside=[.08,.18,.28,.6]
                samples=[path[round(phase*len(path))] for phase in inside+outside]
                lit=overlay.locator("image").evaluate("""async (el, samples) => {
                    const img=new Image(); img.src=el.getAttribute('href'); await img.decode();
                    const canvas=document.createElement('canvas');
                    canvas.width=img.width; canvas.height=img.height;
                    const ctx=canvas.getContext('2d'); ctx.drawImage(img,0,0);
                    return samples.map(([x,y])=>ctx.getImageData(x-22,y-22,45,45).data
                        .some((v,i)=>i%4===3 && v>180));
                }""",samples)
                assert lit==[True]*len(inside)+[False]*len(outside)
                struct.pack_into("<I",session_packet,23,12)
                for i in range(len(posts)):
                    session_packet[52+5*i]=0
                sender.sendto(session_packet,address)
                expect(overlay).to_have_count(0)
                button = bytearray(45)
                button[:29] = wire[2][:29]
                button[6] = 3
                button[29:33] = b"BUTN"
                for number, tab in [(3,"Live Timing"),(1,"Session Analysis"),(2,"Live Timing"),(2,"My Race")]:
                    for mask in (0, 1 << (19 + number)):
                        struct.pack_into("<I",button,33,mask)
                        sender.sendto(button,address)
                    expect(page.get_by_role("navigation").get_by_role("button", name=tab,exact=True)).to_have_attribute("aria-current","page")
                expect(page.get_by_label("Race phase")).to_have_text(name)
            expect(page.get_by_label("Race phase")).to_have_text(name)
            if name == "Race":
                expect(page.get_by_role("region", name="Strategy comparison")).to_be_visible()
                button[:29] = wire[2][:29]
                button[6] = 3
                ask = page.get_by_role("button",name="Request Codex plan",exact=True)
                expect(ask).to_be_enabled()
                assert not advisor_requests
                for mask in (0, 1 << 22, 1 << 22):
                    struct.pack_into("<I",button,33,mask)
                    sender.sendto(button,address)
                deadline = monotonic()+4
                while not advisor_requests and monotonic()<deadline:
                    page.wait_for_timeout(50)
                assert len(advisor_requests)==1, advisor_requests
                ask.click()
                deadline = monotonic()+4
                while len(advisor_requests)<2 and monotonic()<deadline:
                    page.wait_for_timeout(50)
                assert advisor_requests == [advisor_requests[0]]*2, advisor_requests
                for action, check in [(6,"select"),(9,"apply"),(4,"back")]:
                    for mask in (0, 1 << (19 + action)):
                        struct.pack_into("<I",button,33,mask)
                        sender.sendto(button,address)
                    if check=="select":
                        expect(page.get_by_label("Plan B preview")).to_be_visible()
                    elif check=="apply":
                        expect(page.locator(".weather-call")).to_contain_text("Plan B")
                    else:
                        expect(page.get_by_role("button",name="Confirm Plan B")).to_have_count(0)
            else:
                expect(page.locator(".race-state b")).to_contain_text("20:34")
                expect(page.locator(".weather-call, .plan-actions, .pace-line")).to_have_count(0)
        page.get_by_role("button", name="Live Timing", exact=True).click()
        tracks = json.loads((Path(__file__).resolve().parents[1] / "assets/game-circuits/tracks.json").read_text(encoding="utf-8"))
        paths = json.loads((Path(__file__).resolve().parents[1] / "assets/boxbox/image-paths.json").read_text())
        assert set(map(int, tracks)) == {0,2,3,4,5,6,7,9,10,11,12,13,14,15,16,17,19,20,26,27,29,30,31,32,39,40,41,42}
        for track_id, track in tracks.items():
            wire = packets(2026, uid=100+int(track_id))
            wire[1][36] = int(track_id)
            # A narrow local warning and a stationary car at its midpoint.
            wire[1][47] = 3
            for i, post in enumerate([(0,0), (.0625,3), (.125,0)]):
                struct.pack_into("<fb", wire[1], 48+i*5, *post)
            for slot in (0,1):
                struct.pack_into("<f", wire[2], 29+57*slot+20, 5900*45/480)
            for payload in wire.values():
                sender.sendto(payload, address)
            expect(page.locator(".session h1")).to_have_text(track["officialName"])
            art = page.locator(".circuit-art")
            expect(art).to_have_attribute("href", f"/circuits/timing/{track['id']}.webp")
            assert art.evaluate("""async el => {
                const img = new Image(); img.src = el.getAttribute('href'); await img.decode();
                return img.naturalWidth > 1000;
            }""")
            expect(page.locator("[data-marker][transform]")).to_have_count(2)
            path = paths[track["id"]]
            direction = -1 if track.get("reverse") else 1
            x, y = path[direction*45]
            expect(page.locator('[data-marker="HAM"]')).to_have_attribute("transform", f"translate({x:.2f} {y:.2f})")
            overlay = page.locator("[data-yellow-intervals] image")
            expect(overlay).to_have_count(1)
            assert overlay.evaluate("""async (el, [inside,outside]) => {
                const img=new Image(); img.src=el.getAttribute('href'); await img.decode();
                const ctx=document.createElement('canvas').getContext('2d');
                ctx.canvas.width=img.width; ctx.canvas.height=img.height; ctx.drawImage(img,0,0);
                const lit=([x,y])=>ctx.getImageData(x-25,y-25,51,51).data.some((v,i)=>i%4===3 && v>160);
                return lit(inside) && !lit(outside);
            }""", [path[direction*45], path[direction*245]]), track["officialName"]
            assert art.evaluate("""async (el, [slug, origin, path]) => {
                const rim = new Image(); rim.src = '/circuits/flag-edges/'+slug+'.png';
                await rim.decode();
                const ctx = document.createElement('canvas').getContext('2d');
                ctx.canvas.width = rim.width; ctx.canvas.height = rim.height;
                ctx.drawImage(rim,0,0);
                const [x,y] = origin.map(Math.round);
                if (ctx.getImageData(x-3,y-3,7,7).data.some((v,i)=>i%4===3 && v>100)) return false;
                if (slug === 'marina-bay') {
                    const alpha=(px,py)=>ctx.getImageData(px,py,1,1).data[3];
                    for (let px=924; px<=927; px++)
                        for (let py=518; py<=526; py++)
                            if (alpha(px,py)!==alpha(px+36,py+2)) return false;
                }
                if (slug !== 'las-vegas' && slug !== 'marina-bay') return true;
                const source = new Image(); source.src = el.getAttribute('href'); await source.decode();
                ctx.clearRect(0,0,ctx.canvas.width,ctx.canvas.height);
                ctx.drawImage(source,0,0);
                if (slug === 'marina-bay') {
                    // Compare the blue ink centroid through the old T17–18 symbol
                    // with the same pixel phase in the neighbouring unlabelled straight.
                    function blueCenter(px) {
                        let sum=0, mass=0;
                        for (let py=493; py<520; py++) {
                            const [r,,b]=ctx.getImageData(px,py,1,1).data;
                            const weight=Math.max(0,b-r-10);
                            sum+=py*weight; mass+=weight;
                        }
                        return sum/mass;
                    }
                    for (let px=915; px<=935; px++)
                        if (!(Math.abs(blueCenter(px)+2-blueCenter(px+36))<.25)) return false;
                    // All three original leader lines crossed a white rim. Check its
                    // continuity on the exact scanline previously cut by the label mask.
                    return [[1080,167,1,0],[870,467,1,0],[925,505,0,1]].every(([x,y,dx,dy])=>
                        Array.from({length:11},(_,i)=>i+12).some(d=>{
                            const [r,g,b,a]=ctx.getImageData(x+d*dx,y+d*dy,1,1).data;
                            return Math.min(r,g,b)*a/255>165;
                        }));
                }
                return path.every(([px,py])=>{
                    const [r,g,b]=ctx.getImageData(Math.round(px),Math.round(py),1,1).data;
                    return r>135 && g<90 && b>55 && b>g*1.5;
                });
            }""", [track["id"], path[0], path[12:60]]), track["officialName"]
        from test_recordings import drive_stop
        for seq,(pit,pos) in enumerate(((False,2),(True,2),(False,1)),10):
            drive_stop(2026,address,sender,7777,seq,pit,pos,seq==10)
            sleep(.15)
        page.get_by_role("button",name="My Race",exact=True).click()
        result = page.get_by_role("region",name="Pit rejoin comparison")
        expect(result).to_have_count(0)
        page.get_by_role("button",name="Session Analysis",exact=True).click()
        sessions=page.get_by_label("Recorded session",exact=True)
        option=sessions.locator('option[value$="-0000000000001e61"]')
        expect(option).to_have_count(1)
        sessions.select_option(option.get_attribute("value"))
        entry = result.locator("tbody td")
        expect(entry.first).to_contain_text("L7")
        expect(entry.nth(1)).to_have_text("P2 · 1자리 앞")
        expect(entry.nth(2)).to_have_text("P2 · 1자리 앞")
        expect(entry.last).to_have_text("P1")
        page.get_by_role("button",name="Open in My Race").click()
        page.get_by_role("button",name="Race result").click()
        expect(page.locator(".session small")).to_have_text("Replay")
        expect(result).to_have_count(0)
        drive_stop(2026,address,sender,7777,13,False,1)
        page.get_by_role("button",name="Return to live").click()
        expect(page.locator(".session small")).to_have_text("Live")
    page.close()


def run(url, output):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        errors, connections = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        requests = []
        def connected_socket(ws):
            connections.append(ws.url)
            def sent(payload):
                command=json.loads(payload)
                if command.get("type")=="confirm":
                    requests.extend(command["stops"])
            ws.on("framesent",sent)
        page.on("websocket", connected_socket)
        page.goto(url+"?source=demo")
        expect(page.locator("tbody tr")).to_have_count(24)
        check_tyre_badges(page.locator(".tower"))
        page.get_by_role("button",name="Menu",exact=True).click()
        page.get_by_role("button",name="Settings").click()
        settings = page.get_by_role("dialog", name="Settings")
        settings.get_by_text("Keyboard shortcuts").click()
        expect(settings.locator("kbd",has_text="Enter")).to_be_visible()
        page.keyboard.press("Escape")
        expect(settings).to_have_count(0)
        page.get_by_role("button", name="Select SEO").click()
        page.keyboard.press("2")
        phase = page.get_by_label("Race phase")
        def advance_to(mode):
            offsets = {"grid":0, "race":server.GRID_SECONDS, "dnf":server.GRID_SECONDS+server.LAPS*server.DURATION}
            server.demo_elapsed = lambda: offsets[mode]
            expect(phase).to_have_text({"grid":"Pre-race","race":"Racing","dnf":"DNF"}[mode])
        plan = page.locator(".weather-call")
        choices = page.locator(".plan-choice")
        for width, height in ((1920,1080),(1576,883)):
            page.set_viewport_size({"width":width,"height":height})
            advance_to("grid")
            expect(choices.first).to_contain_text("Plan A")
            advance_to("race")
            expect(page.get_by_role("button",name="Custom stop")).to_have_count(0)
            page.locator("body").click(position={"x":1,"y":1})
            page.keyboard.press("ArrowDown")
            expect(page.locator(".plan-choice").nth(1)).to_have_attribute("aria-pressed","true")
            expect(plan).to_contain_text("L21")
            planned_tyre = plan.locator('[data-compound="H"]')
            expect(planned_tyre).to_have_text("H")
            expect(planned_tyre).to_have_css("border-radius","50%")
            check_tyre_badges(page.locator(".my-race"))
            expect(page.locator(".neighbors tbody tr.me")).to_contain_text("8YOU")
            expect(page.locator(".pace")).to_contain_text("4랩 이내 1초 진입 예상")
            expect(plan).to_contain_text("Est. rejoin")
            expect(plan.get_by_label("Pit exit forecast")).to_be_visible()
            check_layout(page,width,height)
            page.screenshot(path=output/f"B-my-race-{width}x{height}.png")
            page.keyboard.press("Escape")
            expect(plan).to_contain_text("L21")
            page.keyboard.press("1")
            expect(page.locator('[data-selected="true"]')).to_have_attribute("data-marker","SEO")
            expect(page.locator("tbody tr")).to_have_count(24)
            expect(page.locator("[data-event]")).to_have_count(6)
            page.screenshot(path=output/f"A-live-{width}x{height}.png")
            page.keyboard.press("2")

        page.get_by_role("button",name="Menu",exact=True).click()
        page.get_by_role("button",name="Settings").click()
        dialog = page.get_by_role("dialog")
        print("SDL before virtual attachment:",dialog.locator("p").first.inner_text(),flush=True)
        wheel = VirtualWheel()
        try:
            for label, control, value in [("Live Timing",55,1),("My Race",56,1),("Next screen",54,1),("Previous screen",53,1),("Move up","hat",1),
                                          ("Move down","hat",4),("Increase","hat",2),("Decrease","hat",8),
                                          ("Confirm",2,1),("Cancel",3,1)]:
                dialog.get_by_label("Bind "+label).click()
                wheel.press(control,value)
                expect(dialog.get_by_role("status")).to_have_text("매핑 저장됨")
            dialog.get_by_role("button",name="Close").click()
            page.reload()
            expect(page.locator("tbody tr")).to_have_count(24)
            analysis = page.get_by_role("main",name="Session Analysis")
            wheel.press(53,1)
            expect(analysis).to_be_visible()
            wheel.press(54,1)
            expect(page.locator(".tower tbody tr")).to_have_count(24)
            wheel.press(56,1)
            advance_to("grid")
            wheel.press(54,1)
            expect(analysis).to_be_visible()
            check_wheel_analysis(analysis,wheel)
            wheel.press(53,1)
            expect(choices.first).to_be_visible()
            wheel.press(54,1)
            wheel.press(3,1)
            expect(choices.first).to_contain_text("Plan A")
            advance_to("race")
            expect(page.get_by_role("button",name="Custom stop")).to_have_count(0)
            wheel.press("hat",4,.45)
            expect(page.locator(".plan-choice").nth(1)).to_have_attribute("aria-pressed","true")
            wheel.press(3,1)
            expect(plan).to_contain_text("L21")
            wheel.press("hat",4)
            expect(page.get_by_label("Plan B preview")).to_be_visible()
            expected = page.locator(".plan-table tr[data-active=true] .schedule-stop .tyre-badge").first.get_attribute("data-compound")
            wheel.press(2,1)
            expect(plan.locator(".tyre-badge").first).to_have_attribute("data-compound",expected)
            wheel.press(55,1)
            expect(page.locator("tbody tr")).to_have_count(24)
            wheel.press(56,1)
            expect(plan.locator(".tyre-badge").first).to_have_attribute("data-compound",expected)
            advance_to("grid")
            expect(choices.first).to_contain_text("Plan A")
            wheel.press(2,1)
            expect(plan).to_contain_text("L14")
            expect(page.get_by_role("button",name="Edit stops")).to_have_count(0)
            check_layout(page,1576,883)
            advance_to("race")
            for _ in range(2):
                wheel.press("hat",4)
            expect(page.get_by_role("button",name="Plan C · Overcut")).to_have_attribute("aria-pressed","true")
            recommended = page.locator(".plan-table tr:has(.plan-rec)")
            for seconds in (44,45,54,72,85,99):
                server.demo_elapsed = lambda: server.GRID_SECONDS + seconds
                expected = server.timing_snapshot(seconds, "race", "M", ((14,"H"),))
                model = expected["forecast"]
                best = next(p for p in model["plans"] if p["id"] == model["recommended"])
                expect(recommended.get_by_role("button")).to_contain_text("Plan "+best["id"])
                expect(recommended.locator(".tyre-badge").first).to_have_text(best["stop"]["tyre"])
                rows = page.get_by_role("region",name="Strategy comparison").locator("tbody tr:has(.plan-choice)")
                for i, candidate in enumerate(model["plans"]):
                    first, last = candidate["window"]
                    low, high = candidate["finish"]
                    cells = rows.nth(i).locator("td")
                    expect(cells.nth(1)).to_contain_text("L"+str(candidate["stop"]["lap"]))
                    expect(cells.nth(2)).to_have_text(f"L{first}–{last}" if first!=last else f"L{first}")
                    expect(cells.nth(3)).to_have_text(f'P{candidate["scenarioRanks"][2]}')
                check_tyre_badges(recommended)
                expect(plan.locator(":scope > span")).to_have_count(0)
                if seconds == 54:
                    page.screenshot(path=output/"my-race-rain.png")
            server.demo_elapsed = lambda: server.GRID_SECONDS + 54
            expect(recommended.locator(".tyre-badge").first).to_have_text("I")
            wheel.press(2,1)
            expect(plan).to_contain_text("L24 I")
            check_wheel_recommended_plan(page,wheel,requests)
            advance_to("dnf")
            expect(page.locator(".battle-stats")).to_contain_text("DNF")
            expect(page.locator(".pace")).to_contain_text("분석 대기")
            expect(page.locator(".plan-actions")).to_have_count(0)
            active_count = len(connections)
            wheel.press(55,1)
            wheel.press(56,1)
            assert len(connections)==active_count==2  # Reload only, never on tab/scene switch.
        finally:
            wheel.close()

        # Feed the production snapshot generator's exact boundary frames to the same UI.
        replay = browser.new_page()
        sockets = []
        def send(at, player="YOU"):
            frame = server.timing_snapshot(at)
            frame["player"] = next(i for i,c in enumerate(frame["cars"]) if c["code"] == player)
            sockets[-1].send(json.dumps(dict(frame,plan=server.Plan().wire(),token=str(at),notice="",
                                              wheel={"keys":[],"device":"","bindings":{}})))
        def connected(ws):
            sockets.append(ws)
            send(0)
        replay.route_web_socket("**/ws/demo",connected)
        replay.goto(url+"?source=demo")
        expect(replay.locator("tbody tr")).to_have_count(24)
        replay.set_viewport_size({"width":819,"height":883})
        expect(replay.locator("nav button")).to_have_text(["Live Timing","My Race","Session Analysis"])
        def badge_metrics(badge):
            return badge.evaluate("""el => {
                const outer = el.getBoundingClientRect(), inner = el.querySelector('b').getBoundingClientRect();
                return [outer.width, outer.height, inner.left-outer.left, outer.right-inner.right,
                    inner.top-outer.top, outer.bottom-inner.bottom, getComputedStyle(el.querySelector('.rank')).font,
                    getComputedStyle(el.querySelector('b')).font, getComputedStyle(el.querySelector('.name-frame')).borderWidth];
            }""")
        timing_metrics = badge_metrics(replay.locator(".tower .rank-driver").first)
        replay.get_by_role("button",name="My Race",exact=True).click()
        expect(replay.locator(".neighbors tbody tr").first).to_contain_text("6HAM")
        pace_rows = replay.locator(".pace-line")
        expect(pace_rows.locator(".rank-driver")).to_have_text(["7ALO", "9GAS"])
        for badge in replay.locator(".my-race .rank-driver").all():
            assert badge_metrics(badge) == timing_metrics
        for player,side in (("VER",1),("SEO",2)):
            send(0,player)
            expect(replay.locator(".neighbors tbody tr")).to_have_count(3)
            expect(replay.locator(".battle-stats strong").nth(side)).to_have_text("—")
            empty_side = replay.locator(".pace-empty")
            expect(empty_side).to_contain_text("앞차 없음" if side == 1 else "뒤차 없음")
            expect(empty_side.locator(".rank-driver")).to_have_count(0)
        for at in (40,47,54,72,103):
            send(at)
            expect(replay.locator(".battle-stats")).to_contain_text("P7")
            expect(replay.locator(".pace-line strong")).to_have_text(["분석 대기"]*2)
            expect(replay.locator(".neighbors tbody tr").first).to_contain_text("5LEC")
            expect(replay.locator(".battle-stats h2").nth(1)).to_have_text("Ahead HAM")
        replay.set_viewport_size({"width":734,"height":883})
        expect(pace_rows.locator(".rank-driver")).to_have_text(["6HAM", "8GAS"])
        for row in pace_rows.all():
            opponent = row.locator(".pace-opponent .rank-driver")
            code = opponent.locator("b").inner_text()
            reference = replay.locator(f'.neighbors tr[data-driver="{code}"] .rank-driver')
            expect(opponent).to_have_css("background-color",reference.evaluate("el => getComputedStyle(el).backgroundColor"))
            badge_box = opponent.bounding_box()
            assert badge_box["y"] + badge_box["height"] <= row.locator("strong").bounding_box()["y"]
        send(103,"ALO")
        badge = replay.locator('.me .rank-driver')
        expect(badge).to_have_css("background-color","rgb(1, 55, 43)")
        replay.keyboard.press("1")
        expect(replay.locator('tr[data-driver="ALO"] .rank-driver')).to_have_css("background-color","rgb(1, 55, 43)")
        expect(replay.locator('tr[data-driver="YOU"] .rank-driver')).to_have_css("background-color","rgb(0, 201, 135)")
        check_live_sessions(browser, url)
        assert not errors, errors
        browser.close()
        print("PASS: both layouts, plan preview/confirm/cancel, grid, DNF, SDL mapping/reload and A/B transitions")


if __name__ == "__main__":
    # Use a dedicated loopback listener; keep the user's running race and bindings intact.
    from tempfile import TemporaryDirectory
    # The game may own the physical wheel exclusively during this virtual-device test.
    sdl = ct.CDLL(str(Path(pygame.__file__).with_name("SDL2.dll")))
    add_device = server.WheelInput.add
    server.WheelInput.add = lambda wheel, index: add_device(wheel,index) if sdl.SDL_JoystickIsVirtual(index) else None
    recording_dir = TemporaryDirectory()
    os.environ["F125_RECORDING_DIR"] = recording_dir.name
    os.environ["F125_UDP_PORT"] = "0"
    output = Path(sys.argv[1]) if len(sys.argv)>1 else Path("output/playwright")
    output.mkdir(parents=True,exist_ok=True)
    listener = socket.socket()
    listener.bind(("127.0.0.1",0))
    port = listener.getsockname()[1]
    server.demo_elapsed = lambda: server.GRID_SECONDS
    app = uvicorn.Server(uvicorn.Config(server.app, log_level="warning"))
    worker = threading.Thread(target=lambda: asyncio.run(app.serve(sockets=[listener])),daemon=True)
    worker.start()
    try:
        deadline = monotonic()+15
        while not app.started and monotonic()<deadline:
            sleep(.05)
        assert app.started
        async def mfd_stub(tyre, valid):
            assert valid()
        server.app.state.game_sync.send=mfd_stub
        run(f"http://127.0.0.1:{port}",output)
    finally:
        app.should_exit=True
        worker.join(5)
        listener.close()
        recording_dir.cleanup()


