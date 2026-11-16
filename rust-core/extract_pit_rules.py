"""Extract the pit timing inputs from an installed GVDB. Writes JSON to stdout.

Usage: python rust-core/extract_pit_rules.py <gamedatabases.2025.bin>
Format reference: https://f1.swofty.net/reference/gamedb/format.html
"""
import hashlib
import json
import struct
import sys
from decimal import Decimal
from pathlib import Path


def records(path):
    raw = path.read_bytes()
    mask = b"tG5MYmBZEZZnrH7yg2qTC4qj42Jcq9"
    pos, stream = 4, 10
    index = {}
    for _ in range(struct.unpack_from("<I", raw)[0]):
        key, _, size = struct.unpack_from("<QBI", raw, pos)
        pos += 13
        if pos + size >= len(raw) or raw[pos + size] != 0:
            raise ValueError("Invalid GVDB record")
        index[key] = (pos, size, stream)
        stream += size
        pos += size + 1
    if pos != len(raw):
        raise ValueError("Unexpected trailing GVDB data")

    def read(name):
        key = 0xcbf29ce484222325
        for byte in name.encode():
            key = ((key ^ byte) * 0x100000001b3) & 0xffffffffffffffff
        offset, size, stream = index[key]
        return bytes((raw[offset+i] - mask[(stream+i) % len(mask)]) % 256
                     for i in range(size)).decode()

    return hashlib.sha256(raw).hexdigest(), read


def extract(path):
    digest, read = records(path)
    root = "pit_crew_training"

    def rows(parent, kind):
        return [f"{parent}.{kind}_{i}" for i in range(int(read(f"{parent}._{kind}_instancecount_")))]

    def ms(field):
        return int(Decimal(read(field)) * 1000)

    profiles = {}
    for group in rows(root+".probabilities", "probability_set"):
        tiers = []
        for entry in rows(group, "probability"):
            tiers.append(dict(training_max=int(read(entry+".max_training_level_percent")),
                              routine=[ms(entry+".min_routine_pit_stop_time"), ms(entry+".max_routine_pit_stop_time")],
                              wing=ms(entry+".estimated_front_wing_change_time"),
                              offsets=[ms(entry+".minigame_pit_stop_time_offset_"+quality)
                                       for quality in ("perfect", "good", "bad")],
                              mistake_possible=int(read(entry+".max_chance_mistake_percent")) > 0))
        profiles[read(group+"._metadata_")] = tiers
    mistakes = {read(row+"._metadata_"): [ms(row+".min_time_loss"), ms(row+".max_time_loss")]
                for row in rows(root+".mistakes", "mistake_info")}
    modes = {read(row+"._metadata_"): read(row+".pit_crew_mistakes_enabled") == "True"
             for row in rows(root+".settings", "settings")}
    return dict(database_sha256=digest, profiles=profiles, mistakes=mistakes, modes=modes)


if __name__ == "__main__":
    print(json.dumps(extract(Path(sys.argv[1])), indent=2))
