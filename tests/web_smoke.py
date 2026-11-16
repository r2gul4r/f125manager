"""Run against a running mock server: python tests/web_smoke.py URL [screenshot.png]."""
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def event_ids(page):
    return page.locator("[data-event]").evaluate_all("(els) => els.map(el => el.dataset.event)")


def check_driver_alignment(page):
    metrics = page.locator(".tower .rank-driver b").evaluate_all("""names => names.map(name => {
        const range = document.createRange();
        range.selectNodeContents(name);
        const text = range.getBoundingClientRect(), cell = name.getBoundingClientRect();
        return [cell.x, cell.width, text.width, text.left-cell.left, cell.right-text.right];
    })""")
    assert len(metrics) == 24
    for values in zip(*(row[:2] for row in metrics)):
        assert max(values)-min(values) < .1, metrics
    assert all(min(left,right) >= 0 and abs(left-right) < .1 for _, _, _, left, right in metrics)
    assert page.locator(".tower .rank").evaluate_all("""ranks => ranks.every(rank => {
        const range = document.createRange();
        range.selectNodeContents(rank);
        const text = range.getBoundingClientRect();
        const badge = rank.parentElement;
        const left = badge.getBoundingClientRect().left + parseFloat(getComputedStyle(badge).borderLeftWidth);
        const right = rank.nextElementSibling.getBoundingClientRect().left;
        return Math.abs((text.left-left)-(right-text.right)) <= 1.5 && text.left >= left && text.right <= right;
    })""")


def check_stint_alignment(page):
    rows = page.locator(".tyre-history").evaluate_all("""rows => rows.map(row =>
        Array.from(row.querySelectorAll('.tyre-badge'), badge => {
            const box = badge.getBoundingClientRect();
            return box.left + box.width / 2;
        }))""")
    assert len(rows) == 24 and all(len(row) == 3 for row in rows)
    for centers in zip(*rows):
        assert max(centers) - min(centers) < .02, centers


def check_nameplate_frame(page):
    assert page.locator(".tower .rank-driver, .sectors .rank-driver").evaluate_all("""badges => {
        function shape(el) {
            const outer = el.getBoundingClientRect(), inner = el.querySelector('b').getBoundingClientRect();
            return [outer.width, outer.height, inner.width, inner.height, inner.x-outer.x, inner.y-outer.y];
        }
        return badges.every(el => {
            const panel = el.closest('.tower, .sectors');
            const expected = shape(panel.querySelector('.rank-driver'));
            const name = el.querySelector('b');
            const frame = el.querySelector('.name-frame');
            const style = getComputedStyle(frame), fill = getComputedStyle(name).backgroundColor;
            const box = frame.getBoundingClientRect(), inner = name.getBoundingClientRect();
            const rank = el.querySelector('.rank').getBoundingClientRect();
            return shape(el).every((n,i)=>Math.abs(n-expected[i]) < .1) &&
                getComputedStyle(el).borderLeftWidth === '0px' &&
                getComputedStyle(el.querySelector('.rank')).borderLeftWidth === '0px' &&
                style.borderLeftWidth === '0px' &&
                rank.right === box.left && rank.top === box.top && rank.bottom === box.bottom &&
                inner.left === box.left && inner.top-box.top >= 2 &&
                [box.right-inner.right,box.bottom-inner.bottom].every(inset=>inset === inner.top-box.top) &&
                (fill !== 'rgb(255, 255, 255)' || getComputedStyle(name).fontWeight === '900') &&
                ['Top','Bottom','Right'].every(side=>style['border'+side+'Width'] === '0px');
        });
    }""")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080}, reduced_motion="reduce")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(sys.argv[1]+"?source=demo")
    rows = page.locator("tbody tr")
    expect(rows).to_have_count(24)
    expect(page.locator(".mini-strip i")).to_have_count(24*3*8)
    expect(page.locator(".tyre-history .tyres")).to_have_count(24*3)
    expect(page.locator("tr[data-driver='SAI'] .tyre-history [data-compound]")).to_have_count(2)
    expect(page.locator(".mini-strip i:not([data-split='pending'])").first).to_be_visible()
    expect(page.get_by_text("Demo", exact=True)).to_be_visible()
    expect(page.locator("[data-marker]")).to_have_count(24)
    expect(page.get_by_role("columnheader", name="PEN", exact=True)).to_have_count(0)
    expect(page.locator("tbody tr td:nth-child(11)")).to_have_count(24)
    expect(page.locator("tbody tr td:nth-child(12)")).to_have_count(0)
    expect(page.locator(".sectors li .rank-driver")).to_have_count(12)
    expect(page.locator(".circuit-art")).to_have_attribute("href", "/circuits/timing/suzuka.webp")
    expect(page.locator("[data-marker] > circle")).to_have_count(24)
    expect(page.locator(".circuit line")).to_have_count(0)
    expect(page.locator(".circuit").locator(":scope > :not(svg)")).to_have_count(0)
    selected = page.locator('[data-marker][data-selected="true"]')
    expect(selected).to_have_attribute("data-marker", "YOU")
    marker = page.locator('[data-marker="SEO"]')
    initial = marker.get_attribute("transform")
    expect(marker).not_to_have_attribute("transform", initial)
    # Sample actual marker transforms on painted frames, independently of WebSocket arrivals.
    movement = marker.evaluate("""node => new Promise(resolve => {
        let start, previous, changes = 0, frames = 0;
        function sample(time) {
            const position = node.getAttribute('transform');
            if (start === undefined) start = time;
            else {
                frames++;
                if (position !== previous) changes++;
            }
            previous = position;
            if (time-start < 2000) requestAnimationFrame(sample);
            else resolve({fps: 1000*changes/(time-start), refresh: 1000*frames/(time-start)});
        }
        requestAnimationFrame(sample);
    })""")
    assert .80 * min(60, movement["refresh"]) < movement["fps"] <= 61, movement
    print(f"Map marker updates per second: {movement['fps']:.1f}")
    page.get_by_role("button", name="Select SEO").click()
    expect(selected).to_have_attribute("data-marker", "SEO")
    page.get_by_role("button", name="Select YOU").click()
    page.set_viewport_size({"width":447,"height":883})
    check_driver_alignment(page)
    penalties = page.locator(".tower .driver-penalties")
    expect(penalties.first).to_be_visible()
    assert penalties.evaluate_all("""labels => labels.every(label => {
        const badge = label.previousElementSibling.getBoundingClientRect();
        const cell = label.closest('td').getBoundingClientRect();
        return badge.left >= cell.left && label.getBoundingClientRect().left - badge.right >= 3
            && label.scrollWidth <= label.clientWidth;
    })""")
    assert page.locator(".tower .rank-driver b").evaluate_all("""names => {
        const boxes = names.map(el=>el.getBoundingClientRect());
        const first = boxes[0];
        return Number.isInteger(first.width) && Number.isInteger(first.height) &&
            boxes.every(r=>r.height === first.height && Number.isInteger(r.top-first.top));
    }""")
    page.set_viewport_size({"width":734,"height":883})
    check_driver_alignment(page)
    assert page.locator(".event-log li").evaluate_all("""items => items.every(el => {
        const id = el.querySelector('.event-id').getBoundingClientRect();
        return el.querySelector('.event-info').getBoundingClientRect().left - id.right >= 8;
    })""")
    for width in (819,1396):
        page.set_viewport_size({"width":width,"height":883})
        check_driver_alignment(page)
        check_stint_alignment(page)
        check_nameplate_frame(page)
    for width, height in [(1920, 1080), (1576, 883), (1280, 720), (1366, 768), (2560, 1440)]:
        page.set_viewport_size({"width": width, "height": height})
        check_driver_alignment(page)
        check_stint_alignment(page)
        check_nameplate_frame(page)
        expect(page.locator("[data-event]")).to_have_count(12)
        panels = [page.locator(selector).bounding_box() for selector in (".circuit", ".sectors", ".event-log")]
        assert page.locator(".sectors .rank-driver").evaluate_all("""badges => badges.every(el => {
            const main = document.querySelector('tr[data-driver="' + el.querySelector('b').textContent + '"] .rank-driver');
            return getComputedStyle(el).font === getComputedStyle(main).font &&
                getComputedStyle(el).backgroundColor === getComputedStyle(main).backgroundColor &&
                el.textContent.startsWith(String([...el.closest('ol').children].indexOf(el.parentElement) + 1));
        })""")
        if width == 1920:
            for panel, size in [(".tower", [84, 32, 48, 4]), (".sectors", [83, 30, 46, 3])]:
                assert page.locator(f"{panel} .rank-driver").first.evaluate("""el => {
                    const outer = el.getBoundingClientRect(), name = el.querySelector('b').getBoundingClientRect();
                    return [outer.width, outer.height, name.width, outer.right-name.right];
                }""") == size
        track = page.locator(".circuit-art").bounding_box()
        assert track["width"] >= .92 * panels[0]["width"]
        assert abs(panels[0]["x"] / width - .637) < .01
        assert track["height"] >= .72 * panels[0]["height"]
        header = page.locator("header").bounding_box()
        title = page.locator("#event-title").bounding_box()
        assert header["height"] <= height * .051
        assert panels[1]["height"] < height * .15
        assert panels[2]["height"] > height * .30
        assert title["height"] < height * .032
        print(f"header={header['height']:.0f}, sectors={panels[1]['height']:.0f}, "
              f"events={panels[2]['height']:.0f}, event title={title['height']:.0f}")
        expect(page.locator(".event-detail")).to_have_count(12)
        assert page.locator(".event-log li").evaluate_all("""els => els.every(el => {
            const heading = el.querySelector('.event-heading').getBoundingClientRect();
            const detail = el.querySelector('.event-detail').getBoundingClientRect();
            const id = el.querySelector('.event-id').getBoundingClientRect();
            return id.right < heading.left && Math.abs(heading.left-detail.left) < 1 &&
                heading.bottom <= detail.top + 1 && detail.bottom <= el.getBoundingClientRect().bottom;
        })""")
        assert page.locator(".event-id:has(.rank-driver)").evaluate_all("""els => els.every(el => {
            const range = document.createRange();
            range.selectNodeContents(el.querySelector('small'));
            return el.querySelector('.rank-driver').getBoundingClientRect().left - range.getBoundingClientRect().right >= 5;
        })""")
        assert page.locator(".event-info").evaluate_all("""els => els.every(el =>
            el.clientWidth > 0 && el.getBoundingClientRect().right <= el.closest('li').getBoundingClientRect().right + 1)""")
        assert page.evaluate("""() => document.documentElement.scrollHeight <= innerHeight &&
            document.documentElement.scrollWidth <= innerWidth""")
        for i, code in [(22, "KIM"), (23, "SEO")]:
            assert rows.nth(i).get_attribute("data-driver") == code
            box = rows.nth(i).bounding_box()
            assert box["y"] + box["height"] <= height
        bounds = page.locator("[data-event]").evaluate_all("""els => els.map(el=>{
            const r=el.getBoundingClientRect();return [r.x,r.y];
        })""")
        event_height = bounds[1][1] - bounds[0][1]
        table_height = rows.first.bounding_box()["height"]
        assert 1.1 < event_height / table_height < 1.5
        print(f"event row={event_height:.1f}px, timing row={table_height:.1f}px")
        for i, (x, y) in enumerate(bounds):
            assert abs(x - bounds[(i // 6) * 6][0]) < 1
            assert abs(y - (bounds[0][1] + event_height * (i % 6))) < 1
        assert bounds[6][0] > bounds[0][0]
        print(f"{width}x{height}: 24 drivers, sidebar x={panels[0]['x']:.0f}, "
              f"sectors y={panels[1]['y']:.0f}, events y={panels[2]['y']:.0f}, 12 recent events")
    page.set_viewport_size({"width": 1920, "height": 1080})
    expect(page.locator("[data-event]")).to_have_count(12)
    for attempt in range(2):  # A looping race can reset the feed between observations.
        before = event_ids(page)
        page.wait_for_function("id => document.querySelector('[data-event]').dataset.event !== id",
                               arg=before[0], timeout=30000)
        after = event_ids(page)
        if after[1:] == before[:-1] and before[-1] not in after:
            break
    else:
        raise AssertionError("event history did not advance one slot")
    highlighted = page.locator(".new-event")
    expect(highlighted).to_have_count(1)
    expect(highlighted).to_have_attribute("data-event", after[0])
    if len(sys.argv) > 2:
        page.screenshot(path=str(Path(sys.argv[2])))
    expect(highlighted).to_have_count(0, timeout=3000)
    assert not errors, errors
    # Replay five race-control cues together so even the older sector yellow is visible.
    replay = browser.new_page(viewport={"width": 1280, "height": 720})
    import json
    from websockets.sync.client import connect
    with connect(sys.argv[1].replace("http", "ws", 1).rstrip("/") + "/ws/demo") as ws:
        frame = json.loads(ws.recv())
    labels = ["세이프티카", "VSC 발령", "옐로 플래그", "그린 플래그", "레드 플래그"]
    frame["events"] = [{"id": str(i), "lap": 20, "driver": "", "label": label, "detail": detail}
                       for i, (label, detail) in enumerate(zip(labels, [
                           "SC 투입 · 대열 주행", "VSC 시작 · 감속 주행",
                           "S2 황색기 · 추월 제한", "S2 황색기 해제", "세션 중단"]))] + frame["events"][:11]
    rulings = [("YOU", "black_white", "흑백기 경고", "트랙 리밋 반복 위반", 0),
               ("GAS", "time", "시간 페널티", "충돌 유발", 5),
               ("HUL", "drive_through", "드라이브스루", "피트 출구 적색등 위반", 0),
               ("KIM", "stop_go", "스톱 앤 고", "세이프티카 규정 위반", 10)]
    frame["events"][5:9] = [
        {"id": f"ruling-{i}", "lap": 20, "driver": driver, "ruling": kind,
         "label": label, "detail": reason, "seconds": seconds}
        for i, (driver, kind, label, reason, seconds) in enumerate(rulings)]
    sockets = []
    def replay_connection(ws):
        sockets.append(ws)
        ws.send(json.dumps(frame))

    replay.route_web_socket("**/ws/demo", replay_connection)
    replay.goto(sys.argv[1]+"?source=demo")
    for i, code in enumerate(["SC", "VSC", "yellow", "green", "red"]):
        badge = replay.locator("[data-event]").nth(i).locator(".control-badge")
        if i < 2:
            expect(badge).to_have_text(code)
            expect(badge).to_have_css("border-top-color", "rgb(255, 144, 0)")
            expect(badge.locator("svg")).to_have_count(0)
        else:
            expect(badge).to_have_attribute("data-flag", code)
            expect(badge).to_be_visible()
            expect(badge.locator("*")).to_have_count(0)
            fill = {"yellow": "rgb(255, 250, 0)", "green": "rgb(0, 239, 87)", "red": "rgb(255, 20, 12)"}
            expect(badge).to_have_css("background-color", fill[code])
        assert badge.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    signals = frame["events"][:5]
    frame["events"] = frame["events"][5:9]
    sockets[-1].send(json.dumps(frame))
    for i, expected in enumerate(["", "+5s", "DT", "S/G 10s"]):
        row = replay.locator(f'[data-event="ruling-{i}"]')
        car = next(c for c in frame["cars"] if c["code"] == rulings[i][0])
        badge = row.locator(".event-id .rank-driver")
        expect(badge.locator("b")).to_have_text(car["code"])
        expect(badge.locator(".rank")).to_have_text(str(car["position"]))
        expect(row.locator(".event-detail")).to_have_text(rulings[i][3])
        if expected:
            expect(row.locator(".ruling-code")).to_have_text(expected)
        else:
            expect(row.locator(".warning-flag")).to_be_visible()
    if len(sys.argv) > 3:
        frame["events"] = signals + frame["events"]
        sockets[-1].send(json.dumps(frame))
        expect(replay.locator(".control-badge")).to_have_count(5)
        replay.set_viewport_size({"width": 1920, "height": 1080})
        first = replay.locator("[data-event]").first.bounding_box()
        last_signal = replay.locator("[data-event]").nth(4).bounding_box()
        replay.screenshot(path=sys.argv[3], clip={"x": first["x"], "y": first["y"],
                          "width": first["width"], "height": last_signal["y"] + last_signal["height"] - first["y"]})
    if len(sys.argv) > 4:
        frame["events"] = [e for e in frame["events"] if e.get("ruling")]
        replay.reload()
        expect(replay.locator(".warning-flag")).to_be_visible()
        first = replay.locator("[data-event]").first.bounding_box()
        last = replay.locator("[data-event]").last.bounding_box()
        replay.screenshot(path=sys.argv[4], clip={"x": first["x"], "y": first["y"],
                          "width": first["width"], "height": last["y"] + last["height"] - first["y"]})
    frame.pop("marshalZones", None)  # Legacy demo frames only carried sector flags.
    for flag, sectors, scope, signal in [
        ("YELLOW", [2], "2", "#fffa00"), ("YELLOW", [], "all", "#fffa00"),
        ("VSC", [], "all", "#ff9000"), ("SC", [], "all", "#ff9000"),
        ("RED", [], "all", "#ff140c"),
    ]:
        frame.update(flag=flag, yellowSectors=sectors)
        sockets[-1].send(json.dumps(frame))
        edge = replay.locator(".flag-edges")
        expect(edge).to_have_attribute("data-flag", flag)
        expect(edge).to_have_attribute("data-sectors", scope)
        assert edge.evaluate("el => getComputedStyle(el).getPropertyValue('--signal').trim()") == signal
        expect(edge.locator("feGaussianBlur")).to_have_attribute("stdDeviation","2")
    frame.update(flag="TRACK CLEAR", yellowSectors=[])
    sockets[-1].send(json.dumps(frame))
    expect(replay.locator(".flag-edges")).to_have_count(0)
    you = next(car for car in frame["cars"] if car["code"] == "YOU")
    driver_row = replay.locator('tr[data-driver="YOU"]')
    expect(replay.locator("tbody .rank-driver")).to_have_count(24)
    expect(driver_row.locator(".rank-driver b")).to_have_text("YOU")
    expect(driver_row.locator(".rank")).to_have_text(str(you["position"]))
    picker = page.get_by_role("combobox", name="Demo circuit")
    venues = picker.locator("option").evaluate_all("opts => opts.map(opt=>opt.value)")
    assert len(venues) == len(set(venues)) == 23
    routes = set()
    for venue in venues:
        picker.select_option(venue)
        circuit = page.locator(f'.circuit[data-circuit="{venue}"]')
        expect(circuit.locator("[data-marker]")).to_have_count(24)
        route = circuit.locator(".circuit-art").get_attribute("href")
        assert route == f"/circuits/timing/{venue}.webp" and route not in routes
        size = page.evaluate("""async url => {
            const im = new Image(); im.src = url; await im.decode();
            return [im.naturalWidth, im.naturalHeight];
        }""", route)
        assert size == [1252, 704], (venue, size)
        routes.add(route)
        position = circuit.locator('[data-marker="YOU"]')
        before_position = position.get_attribute("transform")
        expect(position).not_to_have_attribute("transform", before_position)
    picker.select_option("suzuka")
    print("PASS: 23 selectable circuits, unique paths and moving markers")
    browser.close()
    print("PASS: moving cars, selection, sector board, event flow and eviction")
