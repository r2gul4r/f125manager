import json
import struct
import sys
from pathlib import Path

from compression import zstd

d = Path(sys.argv[1])
last = None
for path in sorted(d.glob("*.zst"))[-5:]:
    buf = zstd.decompress(path.read_bytes())
    o = 8
    while o + 10 <= len(buf):
        t, n = struct.unpack_from("<QH", buf, o)
        p = buf[o + 10 : o + 10 + n]
        o += 10 + n
        if p[6] == 10 and 0 <= p[27] < 24:
            k = 29 + p[27] * 46 + 28
            last = [t, int.from_bytes(p[7:15], "little"), *p[k : k + 2]]
print(json.dumps(last))
