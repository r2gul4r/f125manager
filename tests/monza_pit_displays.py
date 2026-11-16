"""Run with the 27-lap Monza recording; all new display samples go to a temporary library."""
import asyncio
import os
import shutil
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


def verify(source):
    replay = f125_core.Replay(source)
    def capture(ms):
        return dict(replay.advance(ms), recordingId=source.name, timingMs=ms, paused=False, ageMs=0)
    times = (850000, 938795, 960000, 1140714)
    snapshots = [capture(ms) for ms in times]
    current = snapshots[0]
    server.native_snapshot = lambda: current
    with TemporaryDirectory(dir="output") as temp, socket.socket() as listener:
        library = Path(temp).resolve() / "recordings"
        directory = library / source.name
        directory.mkdir(parents=True)
        shutil.copyfile(source/"manifest.json", directory/"manifest.json")
        for chunk in source.glob("*.zst"):
            os.link(chunk, directory/chunk.name)
        os.environ.update(F125_RECORDING_DIR=str(library), F125_UDP_PORT="0", F125_PRACTICE_SAVE_DIR=temp)
        listener.bind(("127.0.0.1", 0))
        app = uvicorn.Server(uvicorn.Config(server.app, log_level="warning"))
        thread = threading.Thread(target=lambda: asyncio.run(app.serve(sockets=[listener])), daemon=True)
        thread.start()
        try:
            deadline = monotonic()+10
            while not app.started and monotonic()<deadline:
                sleep(.05)
            assert app.started
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width":1920,"height":1080})
                base = f"http://127.0.0.1:{listener.getsockname()[1]}"
                page.goto(base)
                page.get_by_role("button", name="My Race", exact=True).click()
                for i, snapshot in enumerate(snapshots):
                    current = snapshot
                    expect(page.locator(".race-state b")).to_contain_text(f"LAP {9+i} /")
                    table = page.locator(".after-pit[data-shown-exit]")
                    expect(table).to_be_visible()
                    shown = table.locator("tbody td")
                    rank = shown.nth(1).inner_text()
                    target = int(table.get_attribute("data-shown-exit"))
                    def neighbour(cell):
                        code = cell.locator(".name-frame b")
                        if not code.count():
                            return None, None
                        gap = cell.locator("strong").inner_text().strip("+−s")
                        return code.inner_text(), None if gap=="—" else round(float(gap)*1000)
                    ahead, behind = neighbour(shown.nth(0)), neighbour(shown.nth(2))
                    url = base+"/api/recordings/"+source.name+"/pit-review"
                    for _ in range(10):
                        row = page.request.get(url).json()[0]["forecasts"][i]
                        if row and row["visible"] and row["at"] == times[i]:
                            break
                        page.wait_for_timeout(250)
                    assert row and row["visible"] and row["at"]==times[i], row
                    assert rank == "P"+str(row["position"]) and target == row["target"]
                    assert ahead == (row["before"],row["aheadGapMs"])
                    assert behind == (row["after"],row["behindGapMs"])
                    print("L",9+i,"target",target,rank,ahead,behind, flush=True)
                current = capture(1166042)
                observed = page.get_by_label("Last pit exit")
                expect(observed).to_contain_text("COR · 통과 대기")
                current = capture(1168780)
                expect(observed).to_contain_text("COR · 2.718s")
                current = capture(replay.duration_ms)
                expect(page.get_by_label("Pit forecast review")).to_contain_text("실제 출구")
                actual = page.request.get(url).json()[0]["actual"]
                assert (actual["position"],actual["after"],actual["behindGapMs"]) == (1,"COR",2718)
                page.reload()
                page.get_by_role("button",name="My Race",exact=True).click()
                expect(page.get_by_label("Pit forecast review")).to_contain_text("COR · 2.718s")
                expect(page.get_by_label("Pit forecast review")).to_contain_text("뒤 COR 간격 0.515초 크게")
                expect(page.get_by_label("Pit forecast review")).to_contain_text("피트 손실 실측 없음")
                browser.close()
        finally:
            app.should_exit = True
            thread.join(8)


if __name__=="__main__":
    verify(Path(sys.argv[1]).resolve())
