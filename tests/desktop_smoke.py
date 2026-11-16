"""Run against the built loopback dashboard. Exercise the same URL opened by Start.cmd."""
import json
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Plan, timing_snapshot


def fits(frame):
    overflow = frame.locator("body").evaluate("""body => {
        const root = document.documentElement;
        const failures = [];
        if (root.scrollHeight > innerHeight+1 || root.scrollWidth > innerWidth+1)
            failures.push('document '+root.scrollWidth+'x'+root.scrollHeight);
        for (const el of body.querySelectorAll('.race-strategy,.work-scroll,dialog[open],.plan-detail,button,select,input,.plan-actions,.committed,.race-note,.event-log,.tower tr')) {
            const rect = el.getBoundingClientRect();
            if (!rect.width || !rect.height) continue;
            if (rect.bottom>innerHeight+1 || rect.right>innerWidth+1 || rect.top < -1 || rect.left < -1 ||
                el.scrollHeight>el.clientHeight+2 || el.scrollWidth>el.clientWidth+2)
                failures.push([el.tagName,el.className,el.textContent.slice(0,25),Math.round(rect.bottom),el.scrollHeight-el.clientHeight]);
        }
        return failures;
    }""")
    assert not overflow, overflow


def inspect(page, url, desktop, width, height):
    page.set_viewport_size({"width":width,"height":height})
    sockets = []
    def feed(mode="race"):
        frame = timing_snapshot(54 if mode=="race" else 0, mode)
        plan = Plan(stops=((8,"H"),(16,"S"),(24,"M"))) if mode=="grid" else Plan()
        sockets[-1].send(json.dumps(dict(frame,plan=plan.wire(),token=mode,notice="전략 적용됨",
                                         wheel={"keys":[],"device":"","bindings":{}})))
    def connected(ws):
        sockets.append(ws)
        feed()
    page.route_web_socket("**/ws/demo",connected)
    page.goto(url+("/desktop.html" if desktop else "/")+"?source=demo")
    if desktop:
        box=page.locator("iframe").bounding_box()
        assert box == {"x":0,"y":0,"width":width,"height":height}, box
    frame = page.frames[-1]
    expect(frame.locator(".tower tbody tr")).to_have_count(24)
    fits(frame)
    if desktop or width==1920:
        frame.get_by_role("button",name="Menu",exact=True).click()
        frame.get_by_role("button",name="Settings",exact=True).click()
        settings = frame.get_by_role("dialog",name="Settings")
        if desktop:
            settings.get_by_label("Layout",exact=True).select_option("fit")
            box = page.locator("iframe").bounding_box()
            assert abs(box["width"]-box["height"]*16/9)<1
            assert abs(box["x"]*2+box["width"]-width)<1 and abs(box["y"]*2+box["height"]-height)<1
            page.reload()
            frame = page.frames[-1]
            frame.get_by_role("button",name="Menu",exact=True).click()
            frame.get_by_role("button",name="Settings",exact=True).click()
            settings = frame.get_by_role("dialog",name="Settings")
            expect(settings.get_by_label("Layout",exact=True)).to_have_value("fit")
            settings.get_by_label("Layout",exact=True).select_option("fill")
            assert page.locator("iframe").bounding_box() == {"x":0,"y":0,"width":width,"height":height}
        mode = settings.get_by_label("Window mode")
        mode.select_option("fullscreen")
        page.wait_for_function("document.fullscreenElement === document.documentElement")
        expect(mode).to_have_value("fullscreen")
        mode.select_option("windowed")
        page.wait_for_function("!document.fullscreenElement")
        expect(mode).to_have_value("windowed")
        settings.get_by_role("button",name="Close",exact=True).click()
    frame.get_by_role("button",name="My Race",exact=True).click()
    fits(frame)
    frame.get_by_role("button",name="Plan B · Undercut").hover()
    expect(frame.get_by_label("Plan B preview")).to_be_visible()
    fits(frame)
    if desktop and width==1920:
        page.screenshot(path="output/playwright/desktop-strategy-1920.png")
    feed("grid")
    expect(frame.get_by_role("button",name="Edit starting strategy")).to_have_count(0)
    fits(frame)
    for name in ["Session Analysis","Settings"]:
        if name=="Settings":
            frame.get_by_role("button",name="Menu",exact=True).click()
        frame.get_by_role("button",name=name,exact=True).click()
        dialog=frame.get_by_role("dialog" if name=="Settings" else "main", name=name)
        if name=="Settings":
            for summary in dialog.locator("summary").all():
                summary.click()
        if name=="Session Analysis":
            dialog.locator("summary").click()
            fits(frame)
            dialog.get_by_label("View",exact=True).select_option("replay")
        fits(frame)
        if name=="Settings":
            dialog.get_by_role("button",name="Diagnostics").click()
            fits(frame)
            dialog.get_by_role("button",name="Close",exact=True).click()
    page.close()


if __name__=="__main__":
    url=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8765"
    Path("output/playwright").mkdir(exist_ok=True,parents=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel="chrome")
        for desktop,width,height in [(False,1280,720),(False,1920,1080),(False,2560,1440),
                                     (True,1920,1080),(True,1600,1000),(True,2560,1080)]:
            inspect(browser.new_page(),url,desktop,width,height)
            print("PASS", "app" if desktop else "browser",width,height)
        browser.close()
