"""Run against the built dashboard with the demo server running on localhost."""
import json
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def run(page, url, output):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url+"?source=demo")
    page.get_by_role("button", name="My Race", exact=True).click()
    expect(page.get_by_text("Recent pace")).to_be_visible()
    plan = page.get_by_label("Selected strategy")
    dialog = page.locator("main.tool-screen")
    comparison = page.get_by_role("region",name="Strategy comparison")
    comparison.get_by_role("button", name="Plan B · Undercut").hover()
    expect(comparison.locator(".plan-rec")).to_have_text("Recommended")
    expect(comparison.get_by_label("Conditions")).to_have_count(0)
    expect(comparison.get_by_label("Plan B preview")).to_contain_text("Rejoin")
    page.screenshot(path=output/"my-race-strategy-comparison.png")
    tyre = comparison.locator("tr[data-active=true] .schedule-stop .tyre-badge").first.get_attribute("data-compound")
    comparison.get_by_role("button", name="Plan B · Undercut").click()
    expect(plan.locator(".tyre-badge").first).to_have_attribute("data-compound",tyre)

    def open_tool(name):
        page.get_by_role("button", name=name, exact=True).click()
        expect(dialog).to_have_accessible_name(name)

    open_tool("Session Analysis")
    dialog.get_by_label("Session",exact=True).select_option(label="Bahrain · FP1")
    dialog.get_by_label("Channel").select_option("Brake")
    dialog.get_by_role("slider").press("End")
    expect(dialog.get_by_role("slider")).to_have_value("11")
    expect(dialog.get_by_role("img", name="Brake comparison by lap distance")).to_be_visible()
    expect(dialog.locator("label .tyre-badge")).to_have_count(2)
    dialog.get_by_text("Sector trend · All clean laps").click()
    expect(dialog.get_by_role("columnheader",name="S1 (s)",exact=True)).to_be_visible()
    page.screenshot(path=output/"telemetry-demo.png")
    dialog.get_by_label("View",exact=True).select_option("replay")
    expect(dialog.get_by_label("Session",exact=True).locator("option:checked")).to_have_text("Bahrain · FP1")
    dialog.get_by_label("Search GP").fill("missing")
    expect(dialog).to_contain_text("검색 조건에 맞는 세션이 없음")
    dialog.get_by_label("Search GP").fill("Japan")
    dialog.get_by_label("Session type").select_option("Race")
    dialog.get_by_role("combobox",name="Stint").select_option("2")
    expect(dialog.locator("tbody tr").first.locator(".tyre-badge")).to_have_text(["H","M","H"])
    dialog.get_by_role("button",name="Play",exact=True).click()
    expect(dialog.get_by_role("heading",name="Lap replay · L20")).to_be_visible()
    expect(dialog.get_by_role("button",name="Play",exact=True)).to_be_visible()
    with page.expect_download() as download:
        dialog.get_by_role("button",name="Export session").click()
    saved=json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
    assert saved["source"]=="Demo" and saved["session"]=="Race" and len(saved["laps"])==6
    page.set_viewport_size({"width":447,"height":883})
    assert dialog.evaluate("d=>d.getBoundingClientRect().width<=innerWidth && d.scrollWidth<=d.clientWidth+1")
    page.keyboard.press("Escape")
    page.get_by_role("button",name="Menu",exact=True).click()
    page.get_by_role("button",name="Settings",exact=True).click()
    dialog=page.get_by_role("dialog",name="Settings")
    dialog.get_by_role("button",name="Diagnostics").click()
    dialog.get_by_label("Demo signal").select_option("Disconnected")
    dialog.get_by_label("Fixture format").select_option("2025")
    expect(dialog.locator("dd")).to_contain_text(["2025","Disconnected","0 Hz"])
    page.keyboard.press("Escape")
    expect(page.get_by_role("main",name="My Race")).to_be_visible()
    assert not errors,errors


if __name__=="__main__":
    output=Path("output/playwright")
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel="chrome")
        run(browser.new_page(viewport={"width":1920,"height":1080}),
            sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8765",output)
        print("PASS: strategy preview/commit, telemetry comparison, filtered replay/export and diagnostics")
