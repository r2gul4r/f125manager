"""Refresh adjacent 2026.json from BoxBox results and its replay map sources."""
import html
import json
import math
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

RESULTS = "https://f1-boxbox.com/ko/formula-1/2026/results/"
# Join on circuit identity, as the GP country can differ from the venue.
KEYS = dict(zip(
    "melbourne shanghai suzuka miami montreal monaco catalunya spielberg silverstone "
    "spa-francorchamps hungaroring zandvoort monza madring baku sepang marina-bay "
    "austin mexico-city interlagos las-vegas lusail yas-marina".split(),
    [10,49,46,151,23,22,15,19,2,7,4,55,39,153,144,12,61,9,65,14,152,150,70], strict=True))
# Data modules shipped by the BoxBox replay for keys 12 and 153.
BUNDLES = {"sepang": "2pusyiliv9o5t", "madring": "3csr34gkc0s3y"}


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "f125manager/1.0"}), timeout=30) as response:
        return response.read().decode("utf-8-sig")


def season(page):
    for body in re.findall(r'<script[^>]*>self\.__next_f\.push\((.*?)\)</script>', page, re.S):
        payload = json.loads(body)
        if len(payload) < 2 or not isinstance(payload[1], str):
            continue
        for match in re.finditer(r'"items":(?=\[)', payload[1]):
            items, _ = json.JSONDecoder().raw_decode(payload[1][match.end():])
            if items and all(isinstance(item, dict) and item.get("year") == 2026
                             and item.get("circuitLayoutId") for item in items):
                return sorted(items, key=lambda race: race["round"])
    raise ValueError("BoxBox season schedule missing")


def read_map(circuit):
    if circuit in BUNDLES:
        url = f"https://f1-boxbox.com/_next/static/chunks/{BUNDLES[circuit]}.js"
        module = fetch(url)
        # Parse numeric literals without executing site code.
        data = {axis: json.loads(re.search(rf'\b{axis}:(\[[\deE+.,\s\-]+\])', module)[1])
                for axis in ("x", "y")}
        data["rotation"] = float(re.search(r'\brotation:(-?[\d.]+)', module)[1])
        data["corners"] = []
    else:
        key = KEYS[circuit]
        url = f"https://api.multiviewer.app/api/v1/circuits/{key}/2026"
        data = json.loads(fetch(url))
        if data["circuitKey"] != key:
            raise ValueError(f"{circuit}: mismatched circuit")
    coords = list(zip(data["x"], data["y"], strict=True))
    if len(set(coords)) < 20 or not all(math.isfinite(n) for point in coords for n in point):
        raise ValueError(f"{circuit}: invalid outline")
    corners = [[c["number"], c["trackPosition"]["x"], c["trackPosition"]["y"], c["angle"]]
               for c in data["corners"]]
    return dict(mapSource=url, mapYear=data.get("year"), rotation=data["rotation"],
                coordinates=coords, corners=corners)


def import_race(race):
    url = RESULTS + race["grandPrixId"]
    page = fetch(url)
    titles = re.findall(r'<h3\b[^>]*>([^<]+)</h3>', page)
    card = page[page.rfind("</h3>"):]
    image = re.search(r'<img\b[^>]*src="(https://media\.formula1\.com/[^"]+/track/[^"]+)"', card)
    return dict(id=race["circuitId"], layout=race["circuitLayoutId"], round=race["round"],
                name=html.unescape(titles[-1]), officialName=race["circuitName"],
                lengthKm=race["courseLength"], turns=race["turns"], laps=race["laps"],
                source=url, image=html.unescape(image[1]) if image else None,
                **read_map(race["circuitId"]))


def main():
    page = fetch(RESULTS + "japan")
    races = season(page)
    links = set(re.findall(r'href="/ko/formula-1/2026/results/([a-z0-9-]+)"', page)) | {"japan"}
    if {r["grandPrixId"] for r in races} != links or len(races) != len(links):
        raise ValueError("Schedule and GP navigation disagree")
    with ThreadPoolExecutor(max_workers=3) as pool:
        catalog = list(pool.map(import_race, races))
    if len({r["id"] for r in catalog}) != len(catalog):
        raise ValueError("Duplicate circuit")
    dest = Path(__file__).with_name("2026.json")
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False, mode="w", encoding="utf-8") as f:
        json.dump(catalog, f, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        f.write("\n")
    os.replace(f.name, dest)
    for c in catalog:
        print(c["round"], c["id"], len(c["coordinates"]), len(c["corners"]))


if __name__ == "__main__":
    main()
