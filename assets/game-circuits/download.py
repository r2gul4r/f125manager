"""Refresh local F1 Media artwork referenced by the game's UDP track-ID catalog."""
import json
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image
from clean_artwork import clean
from timing_artwork import render


BASE = Path(__file__).resolve().parent
PUBLIC = BASE.parents[1] / "web" / "public" / "circuits"
ANNOTATIONS = json.loads((BASE/"annotations.json").read_text())
PATHS = json.loads((BASE.parent/"boxbox/image-paths.json").read_text())


def download(track):
    url = track["imageUrl"]
    if urlparse(url).hostname != "media.formula1.com":
        raise ValueError(url)
    request = Request(url, headers={"Accept": "image/webp", "User-Agent": "f125manager/1.0"})
    with urlopen(request, timeout=30) as response:
        original = response.read()
    image = Image.open(BytesIO(original))
    image.load()
    if image.format != "WEBP" or abs(image.width / image.height - 16 / 9) > .02:
        raise ValueError(f"Unexpected circuit image {url}")
    folder = PUBLIC / str(track["imageSeason"])
    folder.mkdir(exist_ok=True)
    target = folder / (track["id"] + ".webp")
    # The SVG uses a common 1252×704 viewBox; the source keeps its original resolution.
    if not target.exists() or target.read_bytes() != original:
        tmp = target.with_suffix(".part")
        tmp.write_bytes(original)
        tmp.replace(target)
    if track.get("timingArtwork"):
        render(track["id"], target, PATHS[track["id"]], PUBLIC)
    else:
        (PUBLIC/"timing").mkdir(exist_ok=True)
        clean(target, PUBLIC/"timing"/target.name, PATHS[track["id"]], ANNOTATIONS[track["id"]])
    return target.name


if __name__ == "__main__":
    tracks = json.loads((BASE / "tracks.json").read_text(encoding="utf-8"))
    unique = {track["imageUrl"]: track for track in tracks.values()}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name in pool.map(download, unique.values()):
            print(name)
