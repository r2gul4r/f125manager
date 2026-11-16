"""Rebuild circuit pit priors from an F1 25 install (offline, Python 3.14+).

python rust-core/extract_track_pits.py "C:/.../F1 25" > rust-core/src/track_pits.json
"""

import bisect
import json
import math
import re
import struct
import sys
from itertools import accumulate, pairwise
from pathlib import Path

from compression.zstd import decompress
from extract_pit_rules import records

# EA UDP track IDs. Reverse circuits have their own world and timing.
CIRCUITS = {
    0: "melbourne",
    2: "shanghai",
    3: "bahrain",
    4: "catalunya",
    5: "monaco",
    6: "montreal",
    7: "silverstone",
    9: "hungaroring",
    10: "spa_francorchamps",
    11: "monza",
    12: "singapore",
    13: "suzuka",
    14: "abu_dhabi",
    15: "texas",
    16: "brazil",
    17: "austria",
    19: "mexico",
    20: "baku",
    26: "zandvoort",
    27: "imola",
    29: "jeddah",
    30: "miami",
    31: "las_vegas",
    32: "losail",
    39: "silverstone_reverse",
    40: "austria_reverse",
    41: "zandvoort_reverse",
    42: "madrid",
}


def resource(archive, suffix):
    with archive.open("rb") as f:
        header = f.read(48)
        if header[:8] != b"ERPK\x03\0\0\0":
            raise ValueError(f"Unsupported ERP: {archive}")
        offset, size, data = struct.unpack_from("<QQQ", header, 16)
        f.seek(offset)
        index = f.read(size)
        (name,) = re.finditer(
            rb"eaid://[^\0]*" + re.escape(suffix.encode()) + rb"\0", index
        )
        fragment = re.search(rb"temp|syst", index[name.end() : name.end() + 100])
        pos, raw_size, packed = struct.unpack_from(
            "<QQ5xQ", index, name.end() + fragment.end()
        )
        f.seek(data + pos)
        payload = decompress(f.read(packed))
        if len(payload) != raw_size:
            raise ValueError(f"Invalid resource size: {archive} {suffix}")
        return payload


def centreline(section):
    gates = re.findall(rb"point2\0([^\0]+)\0point3\0([^\0]+)\0", section)
    points = []
    for edges in gates:
        left, right = ([float(v) for v in s.split(b",")] for s in edges)
        point = tuple((a + b) / 2 for a, b in zip(left, right, strict=True))
        if not points or math.dist(points[-1], point) > 0.01:
            points.append(point)
    lengths = list(
        accumulate((math.dist(a, b) for a, b in pairwise(points)), initial=0)
    )
    return points, lengths


def interpolate(points, lengths, distance):
    i = min(len(points) - 2, bisect.bisect_right(lengths, distance) - 1)
    ratio = (distance - lengths[i]) / (lengths[i + 1] - lengths[i])
    return tuple(a + (b - a) * ratio for a, b in zip(points[i], points[i + 1]))


def main_progress(point, points, lengths):
    candidates = []
    for i, (a, b) in enumerate(pairwise(points)):
        delta = [q - p for p, q in zip(a, b)]
        length = lengths[i + 1] - lengths[i]
        ratio = sum((v - p) * d for v, p, d in zip(point, a, delta)) / length**2
        distance = lengths[i] + min(1, max(0, ratio)) * length
        candidates.append(
            (math.dist(point, interpolate(points, lengths, distance)), distance)
        )
    return min(candidates)[1] / lengths[-1]


def limiter(archive):
    markup = resource(archive, ".trackmarkup")
    zones = []
    for element in markup.split(b"MarkupElement\0")[1:]:
        if b"Type\0pit_lim_on\0" in element:
            zone = re.search(
                rb"Start\0([^\0]+)\0End\0([^\0]+)\0SplineName\0pit_1\0", element
            )
            if zone:
                zones.append(tuple(map(float, zone.groups())))
    start, end = zones[0]
    if len(zones) != 1 or not 0 <= start < end <= 1:
        raise ValueError(f"Ambiguous limiter: {archive}")
    volumes = resource(archive, ".trackspacedata").split(b"VolumeList\0")[1:]
    (main,) = [centreline(v) for v in volumes if b"type\0main\0" in v]
    (pit,) = [centreline(v) for v in volumes if b"type\0pit\0" in v]
    length = pit[1][-1]
    progress = [
        main_progress(interpolate(*pit, fraction * length), *main)
        for fraction in (start, end)
    ]
    if not 0 < (progress[1] - progress[0]) % 1 < 0.35:
        raise ValueError(f"Invalid bypass: {archive}")
    return round((end - start) * length), progress


def reference_ms(archive, progress):
    # First reference lap of the game's virtual-performance time curves.
    data = resource(archive, ".vp_times")
    (count,) = struct.unpack_from("<I", data, 40)
    if data[:4] != b"\x03\0\0\0" or not 200 < count < 3000:
        raise ValueError(f"Unsupported reference curve: {archive}")
    times = struct.unpack_from(f"<{count}f", data, 44)
    if (
        times[0] != 0
        or not 45 < times[-1] < 240
        or not all(a < b for a, b in pairwise(times))
    ):
        raise ValueError(f"Invalid lap times: {archive}")

    def elapsed(fraction):
        index = fraction * (len(times) - 1)
        i = min(int(index), len(times) - 2)
        return times[i] + (index - i) * (times[i + 1] - times[i])

    return round(1000 * ((elapsed(progress[1]) - elapsed(progress[0])) % times[-1]))


def extract(game):
    digest, read = records(game / "game_package/gamedatabases/gamedatabases.2025.bin")
    root = game / "2025_asset_groups/environment_package/tracks"
    table = {}
    for i in range(2):
        group = f"track_data.game_setup.TrackDataSet_{i}"
        series = read(group + "._metadata_")
        for j in range(int(read(group + "._TrackData_instancecount_"))):
            row = f"{group}.TrackData_{j}"
            circuit = read(row + ".track")
            pit = row + ".TrackPitData_0."
            table[series, circuit] = [
                round(float(read(pit + key)) * scale)
                for key, scale in (
                    ("pitSpeedLimit", 1),
                    ("pitStopTime_Dry", 1000),
                    ("pitStopTime_Wet", 1000),
                )
            ]
    tracks = {}
    for track, name in CIRCUITS.items():
        base = root / name
        metres, progress = limiter(base / "wep" / f"{name}_common.erp")
        item = {"name": name, "limiter_metres": metres, "series": {}}
        for series, car in (("f1", "mercedes"), ("f2", "f2_car")):
            if (series, name) not in table:
                continue
            speed, dry, wet = table[series, name]
            for year in (2025, 2026):
                path = base / f"ai/{series}_{year}_vehicle_package/{car}/{car}.erp"
                if path.exists():
                    item["series"][f"{series}_{year}"] = {
                        "kmh": speed,
                        "dry": dry,
                        "wet": wet,
                        "bypass": reference_ms(path, progress),
                    }
        tracks[track] = item
    return {"database_sha256": digest, "tracks": tracks}


if __name__ == "__main__":
    print(json.dumps(extract(Path(sys.argv[1])), indent=2))
