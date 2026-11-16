"""Run with the recorded Bahrain race directory as the sole argument."""
import asyncio
import os
import socket
import sys
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

import uvicorn
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f125_core
import server


def check(recording, output):
    reader = f125_core.Replay(recording)
    opening = reader.advance(65000)
    samples = [reader.advance(ms) for ms in (277900, 283000, 287416, 683000)]
    pit_cycle = [reader.advance(ms) for ms in (1389000, 1395000, 1800000, 1962000)]
    yellow = [reader.advance(ms) for ms in (1684800, 1685600)]
    repair = reader.advance(3430000)
    assert [{c["lap"] for c in s["cars"]} for s in samples] == [{2}, {2, 3}, {2, 3}, {3}]
    # Feed the normal live websocket with recorded snapshots. A pause bit and
    # stream age are injected separately so the UI must handle both cases.
    current = dict(opening, ageMs=0)
    server.native_snapshot = lambda: current
    with socket.socket() as listener, TemporaryDirectory() as record_dir:
        os.environ.update(F125_UDP_PORT="0", F125_RECORDING_DIR=record_dir)
        listener.bind(("127.0.0.1", 0))
        app = uvicorn.Server(uvicorn.Config(server.app, log_level="warning"))
        thread = threading.Thread(target=lambda: asyncio.run(app.serve(sockets=[listener])), daemon=True)
        thread.start()
        try:
            deadline = monotonic() + 10
            while not app.started and monotonic() < deadline:
                sleep(.05)
            assert app.started
            sent = []
            async def capture(tyre, valid):
                assert valid()
                sent.append(tyre)
            server.app.state.game_sync.send = capture
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1920, "height": 1080})
                page.goto(f"http://127.0.0.1:{listener.getsockname()[1]}")
                page.get_by_role("button", name="My Race", exact=True).click()
                box = page.get_by_label("Selected strategy")
                table = page.locator(".plan-comparison tbody")
                expect(page.locator(".pace-line strong")).to_have_text(["현재 1초 이내"]*2)
                expect(table.locator(".plan-choice")).to_have_count(3)
                expect(page.locator(".plan-comparison h3")).to_contain_text("Forecast from L")
                expect(box).to_be_visible()
                expect(page.get_by_text("Projected pit exit", exact=True)).to_have_count(0)
                for snapshot in samples[:3]:
                    current = dict(snapshot, ageMs=0)
                    player = next(c for c in snapshot["cars"] if c["slot"] == snapshot["player"])
                    expect(page.locator(".plan-comparison h3")).to_contain_text(f'L{player["lap"]}')
                    expect(box).to_be_visible()
                    for i, name in enumerate(["Plan A · Balanced", "Plan B · Undercut", "Plan C · Overcut"]):
                        expect(table.locator(".plan-choice").nth(i)).to_have_accessible_name(name)
                b = table.get_by_role("button", name="Plan B · Undercut")
                b.hover()
                preview = page.get_by_label("Plan B preview")
                expect(preview).to_be_visible()
                assert not sent
                tyre = page.locator(".plan-table tr[data-active=true] .schedule-stop .tyre-badge").first.get_attribute("data-compound")
                b.click()
                expect(page.get_by_role("status").filter(has_text="게임 MFD 확인")).to_contain_text(tyre)
                assert sent == [tyre]
                expect(preview.get_by_label("Pit service comparison")).to_contain_text("Est. pit loss")
                expect(box).to_contain_text("Est. rejoin")
                original = box.inner_text()
                for age, paused in [(0, True), (12000, False)]:
                    current = dict(samples[2], ageMs=age, paused=paused)
                    expect(page.locator(".plan-comparison h3")).to_contain_text("Forecast from L3")
                    expect(box).to_be_visible()
                    expect(page.locator(".details-toggle, .plan-detail")).to_have_count(0)
                    assert box.inner_text() == original
                    if paused:
                        page.screenshot(path=output)
                current = dict(samples[3], ageMs=0)
                expect(box).to_be_visible()
                expect(page.get_by_text("마지막 예측", exact=False)).to_have_count(0)
                expect(box).to_be_visible()
                current = dict(pit_cycle[0], ageMs=0)
                expect(page.locator(".plan-comparison h3")).to_contain_text("L3")
                # Wait for the correct attempt even when its lap equals the previous frame.
                expect(page.locator(".battle-stats strong").first).to_have_text("P20")
                original_plans = table.locator(".plan-choice").all_text_contents()
                current = dict(pit_cycle[1], ageMs=0)
                expect(page.locator(".plan-comparison h3")).to_contain_text("Forecast from L3")
                expect(table.locator(".plan-choice").first).to_be_disabled()
                assert table.locator(".plan-choice").all_text_contents() == original_plans
                expect(page.locator(".pit-estimates")).to_have_count(0)
                current = dict(pit_cycle[2], ageMs=0)
                expect(page.locator(".plan-comparison h3")).to_contain_text("L5")
                expect(table.locator(".plan-choice").first).to_be_enabled()
                current = dict(pit_cycle[3], ageMs=0)
                expect(table.locator(".plan-choice").first).to_be_enabled()
                expect(page.locator(".plan-comparison h3")).to_contain_text("L6")
                for snapshot in yellow:
                    current = dict(snapshot, ageMs=0)
                    expect(page.locator(".race-state strong")).to_have_text("YELLOW")
                    expect(box).to_be_visible()
                    expect(page.locator(".pace-line strong").first).to_have_text("랩 평균 대기")
                    expect(page.locator(".pace-line").first).to_contain_text("현재 간격 23.4초")
                    expect(table.locator(".plan-choice").first).to_be_enabled()
                current = dict(yellow[-1], ageMs=25000, paused=True)
                expect(page.locator(".plan-comparison h3")).to_contain_text("Forecast from L4")
                expect(box).to_be_visible()
                expect(page.locator(".pace-line strong").first).to_have_text("랩 평균 대기")
                current = dict(repair, ageMs=0)
                expect(page.get_by_label("Pit rejoin comparison")).to_have_count(0)
                current = dict(samples[2], handoff=True)
                expect(page.get_by_role("status").filter(has_text="Last recording").first).to_be_visible()
                page.get_by_role("button", name="Plan B · Undercut").click()
                expect(page.get_by_label("Plan B details")).to_have_count(0)
                print(f"Bahrain Plan B · L8 {tyre}: hover=0, one click=1", flush=True)
                expect(box).to_contain_text("Plan B")
                expect(page.get_by_role("button", name="Request Codex plan")).to_be_enabled()
                expect(page.get_by_role("button",name="Custom stop")).to_have_count(0)
                assert sent == [tyre]
                browser.close()
        finally:
            app.should_exit = True
            thread.join(5)


if __name__ == "__main__":
    check(Path(sys.argv[1]), Path("output/playwright/bahrain-held-forecast.png"))
