"""Offline .f1bin single-session validation. Python 3.14+ and f125_core required."""
import json
import struct
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from compression import zstd

import f125_core


def compare(path):
    # Run every car from the beginning. A changed viewpoint must never inherit
    # the actual player's game strategy or use a future stop to select a driver.
    with TemporaryDirectory() as folder:
        root = Path(folder)
        with path.open("rb") as source:
            prefix = source.read(10)
            start, length = struct.unpack("<QH", prefix)
            first = source.read(length)
            year, _, uid, _ = f125_core.read_header(first)
            slots = 24 if year == 2026 else 22
            player = first[27]
            source.seek(0)
            buffers = [bytearray() for _ in range(slots)]
            directories = [root / str(i) for i in range(slots)]
            for directory in directories:
                directory.mkdir()
            chunks = 0

            def flush():
                for directory, buf in zip(directories, buffers):
                    (directory / f"{chunks:08}.zst").write_bytes(zstd.compress(b"F125RAW1" + buf))
                    buf.clear()

            packets = 0
            while header := source.read(10):
                stamp, length = struct.unpack("<QH", header)
                b = bytearray(source.read(length))
                if len(b) != length or f125_core.read_header(bytes(b))[::2] != (year, uid):
                    raise ValueError("Expected a complete, single-session capture")
                # Only the original UDP channels needed by the pit estimator.
                if b[6] not in (1, 2, 3, 4, 7, 10):
                    continue
                packets += 1
                ms = (stamp-start)//1_000_000
                if b[6] == 1:
                    strategy = bytes(b[682:685])
                for slot, buf in enumerate(buffers):
                    b[27] = slot
                    if b[6] == 1:
                        b[682:685] = strategy if slot == player else bytes(3)
                    buf.extend(struct.pack("<QH", ms, length))
                    buf.extend(b)
                if len(buffers[0]) >= 512*1024:
                    flush()
                    chunks += 1
            if buffers[0]:
                flush()
                chunks += 1
        for slot, directory in enumerate(directories):
            manifest = {
                "version": 3, "id": str(slot), "uid": str(uid), "format": year,
                "startedMs": start//1_000_000, "durationMs": ms, "track": None,
                "sessionType": None, "pitLossMs": 20000, "chunks": chunks, "packets": packets,
                "stops": [], "epoch": 1,
            }
            (directory/"manifest.json").write_text(json.dumps(manifest))
            reader = f125_core.Replay(directory)
            for lap, rank, actual, entry, exit_ms in reader.advance(ms)["replayedVisits"]:
                at_entry = reader.advance(entry)["replayedVisits"][-1]
                assert at_entry[1] == rank and at_entry[2] is None
                print(f"slot={slot} player={slot==player} lap={lap} estimate={rank} "
                      f"observed={actual} entryMs={entry} exitMs={exit_ms}")


if __name__ == "__main__":
    compare(Path(sys.argv[1]))
