"""Optional offline Kev check. Run with the existing Kev Python and cached weights only."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def check_model():
    import collections

    import torch
    from kev.api import SystemOneRequest
    from kev.checkpoint import Checkpoint
    from kev.serve import Server

    rows = json.loads(sys.stdin.read())
    torch.set_num_threads(3)
    ck = Checkpoint("jaredpalmer/kev-0.8b@54f4f87")
    tok, model = ck.load("cpu")
    svc = Server(ck, tok, model, "cpu", release_date="offline")
    groups = collections.defaultdict(list)
    for own, slot, lap, compound, age, surface, ms, wear in rows:
        groups[slot].append((lap, compound, age, surface, ms))
    options = {
        "faster": "more than 0.5 seconds faster",
        "similar": "within 0.5 seconds",
        "slower": "more than 0.5 seconds slower",
    }

    def label(diff):
        return "faster" if diff < -500 else "slower" if diff > 500 else "similar"

    scores = collections.Counter()
    for slot, records in sorted(groups.items()):
        records.sort()
        for a, b, c in zip(records, records[1:], records[2:]):
            if not (
                a[0] + 1 == b[0] == c[0] - 1
                and a[2] + 1 == b[2] == c[2] - 1
                and a[1] == b[1] == c[1]
                and a[3] == b[3] == c[3]
            ):
                continue
            state = {
                "track": "Bahrain FP1, dry",
                "compound": {16: "soft", 17: "medium", 18: "hard"}[b[1]],
                "completed_tyre_age": b[2] + 1,
                "consecutive_clean_lap_seconds": [a[4] / 1000, b[4] / 1000],
            }
            totals = collections.Counter()
            keys = list(options)
            for offset in range(3):
                order = keys[offset:] + keys[:offset]
                q = {
                    "type": "choice",
                    "instructions": "Forecast the next clean lap time relative to the last completed lap, on the same tyre and in the same conditions.",
                    "criteria": {k: options[k] for k in order},
                }
                ans = svc.answer(SystemOneRequest(state=state, questions={"pace": q}))[
                    "answers"
                ]["pace"]["probabilities"]
                totals.update(ans)
            target = label(c[4] - b[4])
            guess = totals.most_common(1)[0][0]
            scores["cases"] += 1
            scores["kev_correct"] += guess == target
            scores["two_lap_mean_correct"] += label((a[4] - b[4]) / 2) == target
            scores["last_lap_correct"] += target == "similar"
            print(slot, c[0], guess, target, flush=True)
            break
    print(dict(scores), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kev-python", type=Path)
    parser.add_argument("--hf-cache", type=Path)
    parser.add_argument("--inference", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inference:
        check_model()
        return
    if not args.kev_python or not args.hf_cache:
        parser.error(
            "Pass --kev-python and --hf-cache from the local Kev installation."
        )
    import f125_core

    root = Path(__file__).resolve().parents[1]
    fp = f125_core.Replay(root / "data/recordings/1794652872959566-ab7ca29c2725c46e")
    samples = fp.advance(fp.duration_ms)["practiceLaps"]
    env = {
        **os.environ,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HOME": str(args.hf_cache.resolve()),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    subprocess.run(
        [args.kev_python, __file__, "--inference"],
        env=env,
        input=json.dumps(samples),
        text=True,
        check=True,
    )


if __name__ == "__main__":
    main()
