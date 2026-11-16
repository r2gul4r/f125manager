"""Check the offline dashboard against the original Bahrain recordings, using an isolated receiver."""
import asyncio
import os
import socket
import sys
import threading
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

import uvicorn
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def check_race_readability(page):
    for width, height in [(1920, 1080), (1864, 883), (1280, 720), (819, 883), (447, 883)]:
        page.set_viewport_size({"width": width, "height": height})
        page.evaluate("document.fonts.ready")
        stats = page.locator(".battle-stats")
        errors = stats.evaluate("""stats => {
            const issues = [];
            const style = stats.getAttribute('style');
            const normal = [...stats.querySelectorAll('strong')].map(el=>getComputedStyle(el).fontSize);
            if (new Set(normal).size !== 1) issues.push('unequal sizes');
            stats.style.setProperty('--gap-digits','5');
            for (const [i, cell] of [...stats.children].entries()) {
                const value = cell.querySelector('strong');
                const copy = value.cloneNode(false);
                cell.append(copy);
                for (const digit of '0123456789') {
                    copy.textContent = i ? digit.repeat(5) + '.' + digit : 'P' + digit.repeat(2);
                    if (i) copy.append(Object.assign(document.createElement('small'), {textContent:'s'}));
                    const range = document.createRange();
                    range.selectNodeContents(copy);
                    if (range.getBoundingClientRect().right > cell.getBoundingClientRect().right)
                        issues.push(copy.textContent);
                }
                copy.remove();
            }
            stats.setAttribute('style',style);
            return issues;
        }""")
        assert not errors, (width, errors)
        history = page.locator(".race-observations > .pace-history:last-child")
        expect(history.get_by_text("Recent pace", exact=False).first).to_be_visible()
        assert history.locator(".lap-strip").evaluate("""strip => {
            const boxes = [...strip.children].map(cell => cell.getBoundingClientRect());
            const bounds = strip.getBoundingClientRect();
            return boxes.length > 0 && Math.abs(boxes[0].left - bounds.left) < 1 &&
                Math.abs(boxes.at(-1).right - bounds.right) < 1 &&
                boxes.every(box => Math.abs(box.width - boxes[0].width) < 1);
        }"""), width
        if width >= 1280:
            bottom = page.locator(".codex-actions").bounding_box()
            assert bottom["y"] + bottom["height"] <= height + 1, (width, bottom)
    page.set_viewport_size({"width": 1920, "height": 1080})


def check_plan_layout(page):
    table = page.locator(".plan-table")
    expect(table.get_by_role("columnheader", name="Pit window")).to_be_visible()
    for width, height in [(1864, 883), (1280, 720), (447, 883)]:
        page.set_viewport_size({"width": width, "height": height})
        page.evaluate("document.fonts.ready")
        errors = table.evaluate("""table => {
            const issues = [];
            const buttons = [...table.querySelectorAll('.plan-choice')].map(el=>el.getBoundingClientRect());
            if (new Set(buttons.map(r=>[r.x,r.width,r.height].join())).size !== 1) issues.push('plan buttons');
            for (const row of table.tBodies[0].rows) {
                for (const cell of row.cells) {
                    const range = document.createRange();
                    range.selectNodeContents(cell);
                    if (range.getBoundingClientRect().right > cell.getBoundingClientRect().right+1)
                        issues.push(cell.textContent);
                    if (cell.matches('.finish-range') && range.getClientRects().length !== 1)
                        issues.push('split finish');
                }
            }
            return issues;
        }""")
        assert not errors, (width, errors)
        history = page.locator(".race-observations > .pace-history:last-child")
        expect(history.get_by_text("Recent pace", exact=False).first).to_be_visible()
        assert history.locator(".lap-strip").evaluate("""strip => {
            const boxes = [...strip.children].map(cell => cell.getBoundingClientRect());
            const bounds = strip.getBoundingClientRect();
            return boxes.length > 0 && Math.abs(boxes[0].left - bounds.left) < 1 &&
                Math.abs(boxes.at(-1).right - bounds.right) < 1 &&
                boxes.every(box => Math.abs(box.width - boxes[0].width) < 1);
        }"""), width
        if width == 1864:
            page.locator(".plan-comparison").screenshot(path="output/playwright/my-race-plans-1864.png")
    page.set_viewport_size({"width": 1920, "height": 1080})


def check(root, real_codex=False):
    race = "1794660248644479-bcd8c3d49cdcd06f"
    short = "1794655437771935-4e4a5984bb733064"
    with socket.socket() as listener, TemporaryDirectory() as scratch:
        os.environ.update(F125_UDP_PORT="0", F125_RECORDING_DIR=scratch)
        listener.bind(("127.0.0.1", 0))
        address = f"http://127.0.0.1:{listener.getsockname()[1]}"
        loop = asyncio.new_event_loop()
        app = uvicorn.Server(uvicorn.Config(server.app, log_level="warning"))
        thread = threading.Thread(target=loop.run_until_complete, args=(app.serve(sockets=[listener]),))
        thread.start()
        try:
            deadline = monotonic()+15
            while not app.started and monotonic() < deadline:
                sleep(.05)
            assert app.started
            server.app.state.record_dir = root

            def wheel(action):
                def send():
                    for queue in server.app.state.subscribers:
                        queue.put_nowait(action)
                loop.call_soon_threadsafe(send)

            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.add_init_script("""localStorage.setItem('pitwall.sdl.bindings',
                    JSON.stringify({down:'down',right:'right',ok:'ok'}))""")
                page.goto(address+"/?replay="+race)
                page.get_by_role("button", name="Race result").click()
                pit = page.get_by_label("Pit rejoin comparison")
                expect(pit).to_have_count(0)
                expect(page.get_by_label("Pit service scenarios")).to_have_count(0)
                expect(page.get_by_label("Pit exit estimates")).to_have_count(0)
                expect(page.get_by_label("Selected strategy")).to_be_visible()
                check_race_readability(page)
                expect(page.locator(".plan-comparison tbody button")).to_have_count(3)
                expect(page.get_by_role("button", name="Box this lap")).to_have_count(0)
                menu = page.get_by_role("button", name="Race result")
                menu.focus()
                for control in [page.get_by_role("button", name="Return to live"),
                                page.get_by_role("button", name="Plan A · Balanced"),
                                page.get_by_role("button", name="Plan B · Undercut")]:
                    wheel("down")
                    expect(control).to_be_focused()
                wheel("ok")
                expect(control).to_have_attribute("aria-pressed", "true")
                wheel("down")
                expect(page.get_by_role("button", name="Plan C · Overcut")).to_be_focused()
                expect(page.get_by_label("Plan C preview")).to_be_visible()
                expect(page.locator(".details-toggle, .plan-detail")).to_have_count(0)
                page.get_by_role("button", name="Live Timing", exact=True).click()
                expect(page.get_by_role("img", name="positions of", exact=False)).to_be_visible()
                expect(page.get_by_role("columnheader", name="Sector 3", exact=True)).to_be_visible()
                page.get_by_role("button", name="Session Analysis", exact=True).click()
                expect(page.get_by_label("Recorded session")).to_have_value(race)
                expect(page.get_by_text("Lap comparison · Recorded UDP")).to_be_visible(timeout=20000)
                expect(pit).to_contain_text("P21")
                expect(pit).to_contain_text("앞날개 수리")
                expect(pit).to_contain_text("Broadcast")
                expect(pit).to_contain_text("정차 평균 포함")
                cells = pit.locator("tbody tr").first.locator("td")
                expect(cells.nth(0)).to_contain_text("타이어 교체 · 앞날개 수리")
                expect(cells.nth(0)).to_contain_text("Replay · Tyres P22 / + Wing P22")
                expect(cells.nth(2)).to_contain_text("P22 · 1자리 앞")
                expect(cells.nth(3)).to_have_text("P21")
                page.get_by_label("Channel").select_option(label="Brake (%)")
                expect(page.get_by_role("img", name="Brake (%) by lap distance")).to_be_visible()
                page.goto(address+"/?replay="+short)
                page.get_by_role("button", name="Race result").click()
                expect(page.get_by_text("이 재생 시점에 기록된 차량 타이밍 없음")).to_be_visible()
                page.get_by_role("button", name="Session Analysis", exact=True).click()
                expect(page.get_by_text("이 녹화본에 비교할 플레이어 랩 기록 없음")).to_be_visible()
                page.goto(address+"/?replay=1794711347679644-450152b3f1f6e1fc")
                slider = page.get_by_label("Replay time")
                expect(slider).to_be_visible()
                slider.evaluate("""el=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'17000');
                    el.dispatchEvent(new Event('input',{bubbles:true}))}""")
                setup = page.get_by_label("Pre-race recommendation")
                expect(setup).not_to_contain_text("kg")
                expect(setup).to_contain_text("Equal projected time")
                expect(page.get_by_label("Practice tyre measurements")).to_contain_text("119 laps")
                expect(setup.get_by_label("Planned tyre stints")).to_have_count(2)
                expect(page.get_by_role("button",name="Request Codex plan")).to_be_enabled()
                # Only the external SDK response is substituted in the offline check.
                class LocalSdk:
                    def __init__(self, config): pass
                    async def __aenter__(self): return self
                    async def __aexit__(self, *args): pass
                    async def thread_start(self, **options): return self
                    id = "offline-test-thread"
                    async def run(self, facts, **options):
                        assert json.loads(facts)["lap"] == 2 and "pitComparisons" not in facts
                        return SimpleNamespace(error=None,final_response=json.dumps({key:{"lap":lap,"tyre":"M","reason":"테스트 제안"} for key,lap in zip("ABC",(7,6,8))}))
                with nullcontext() if real_codex else patch("gp_advisor.AsyncCodex", LocalSdk):
                    page.goto(address+"/?replay=1794711347679644-450152b3f1f6e1fc")
                    slider = page.get_by_label("Replay time")
                    expect(slider).to_be_visible()
                    slider.evaluate("""el=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'274004');
                        el.dispatchEvent(new Event('input',{bubbles:true}))}""")
                    ask = page.get_by_role("button",name="Request Codex plan",exact=True)
                    expect(ask).to_be_enabled()
                    plans = page.locator(".plan-comparison tr:has(.plan-choice)")
                    expect(plans.nth(0).locator(".stop-sequence")).to_contain_text("L18")
                    expect(plans.nth(0).locator(".stop-sequence small")).to_have_text("2 stops")
                    plans.nth(2).get_by_role("button").hover()
                    expect(page.get_by_label("Plan C preview").locator(".tyre-risk")).to_contain_text("수명")
                    check_plan_layout(page)
                    for _ in range(18):
                        wheel("down")
                        page.wait_for_timeout(160)
                        if ask.evaluate("el=>el===document.activeElement"): break
                    expect(ask).to_be_focused()
                    wheel("ok")
                    choice = page.get_by_role("button",name="Plan A · Balanced")
                    expect(choice.locator("xpath=../..")).to_contain_text("L7",timeout=95000)
                    choice.click()
                    expect(page.get_by_label("Selected strategy")).to_contain_text("Plan A")
                    expect(page.get_by_label("Selected strategy")).to_contain_text("L7")
                    selection = page.get_by_label("Selected strategy")
                    expect(selection.get_by_label("Ahead", exact=True)).to_be_visible()
                    expect(selection.get_by_label("Behind", exact=True)).to_be_visible()
                page.goto(address+"/?replay=1794735823068975-42765713e5577ea7")
                page.get_by_role("button", name="Live Timing", exact=True).click()
                clock = page.get_by_label("Replay time")
                cell = page.locator("tr.player td.live-sector").nth(2)
                for position, expected in [(158500, "27.498"), (164000, "—")]:
                    clock.evaluate("""(el,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(v));
                        el.dispatchEvent(new Event('input',{bubbles:true}))}""", position)
                    expect(cell.locator("span")).to_have_text(expected)
                assert not errors, errors
                browser.close()
            assert server.app.state.udp.snapshot()["accepted"] == 0
        finally:
            app.should_exit = True
            thread.join()
            loop.close()


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve(), "--real-codex" in sys.argv[2:])
