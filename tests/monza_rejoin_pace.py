"""Compare pace inputs against the Monza player's recorded exit. Run with the recording directory."""
import json
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from statistics import mean
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f125_core
from live_timing import live_frame

engine = f125_core.race_forecast


def with_recent_pace(include_player):
    def run(entries, player, *args):
        field = []
        for index, (code, gap, tyre, age, reference, samples) in enumerate(entries):
            # Use the production same-stint clean-lap filter. With fewer than two
            # observations keep the running estimate, including the early-race fallback.
            if len(samples) >= 2 and (index != player or include_player):
                reference = round(mean(ms for _, ms in samples[-3:]))
            field.append((code, gap, tyre, age, reference, samples))
        return engine(field, player, *args)
    return run


def compare(path):
    manifest = json.loads((path / 'manifest.json').read_bytes())
    # A flashback may copy the same completed stop into later epoch summaries.
    stops = {(s['entryMs'], s['exitMs']): s for s in manifest['stops'] if s['exitMs'] is not None}
    for (entry, exit_ms), stop in stops.items():
        replay = f125_core.Replay(path)
        target = stop['lap']
        results = defaultdict(list)
        for ms in sorted({*range(0, entry, 1000), entry - 1}):
            raw = replay.advance(ms)
            frame = live_frame(raw, pit_ms=replay.pit_loss_ms)
            if not frame or not frame['forecast'] or not target - 5 <= frame['lap'] <= target:
                continue
            offset = target - frame['lap']
            variants = [frame]
            for include_player in (False, True):
                with patch.object(f125_core, 'race_forecast', with_recent_pace(include_player)):
                    variants.append(live_frame(raw, pit_ms=replay.pit_loss_ms))
            predictions = [v['forecast']['tyreExits'][offset] for v in variants]
            results[raw['epoch'], frame['lap']].append((ms, predictions))

        before = replay.advance(entry - 1)
        exited = live_frame(replay.advance(exit_ms))
        index = exited['player']
        actual = (exited['cars'][index]['position'],
                  exited['cars'][index - 1]['code'] if index else None,
                  exited['cars'][index + 1]['code'] if index + 1 < len(exited['cars']) else None)
        assert actual[0] == stop['actual']
        print(f'L{target} entry={entry} exit={exit_ms} actual={actual}')
        print('entry forecast:', bool(live_frame(before)['forecast']))
        # Monza's sole missing leader gap is P24's. Its valid interval to P23
        # allows a separate diagnostic reconstruction using entry-time data.
        diagnostic = deepcopy(before)
        cars = sorted((c for c in diagnostic['cars'] if c['result'] == 2), key=lambda c: c['position'])
        if ([c['position'] for c in cars if c['raceGapMs'] is None] == [cars[-1]['position']]
                and cars[-1]['intervalValid'] and cars[-2]['position'] + 1 == cars[-1]['position']):
            cars[-1]['raceGapMs'] = cars[-2]['raceGapMs'] + cars[-1]['intervalMs']
            diagnostic['comparableLaps'] = True
            for model in (engine, with_recent_pace(False), with_recent_pace(True)):
                with patch.object(f125_core, 'race_forecast', model):
                    row = live_frame(diagnostic, pit_ms=replay.pit_loss_ms)['forecast']['tyreExits'][0]
                print('entry reconstruction', row['position'], row['before'], row['after'], row['behindGapMs'])
        print('order: existing / rival mean / all mean')
        totals = [[], [], []]
        for (epoch, lap), samples in results.items():
            metrics = []
            for variant in range(3):
                errors = []
                for _, rows in samples:
                    row = rows[variant]
                    errors.append((abs(row['position'] - actual[0]), (row['before'], row['after']) == actual[1:]))
                totals[variant].extend(errors)
                metrics.append((round(mean(e for e, _ in errors), 2), sum(hit for _, hit in errors)))
            print(f'epoch {epoch} L{lap} n={len(samples)} rank MAE & pair hits={metrics}')
            for ms, rows in samples:
                if ms in (661000, 780000, 850000, 950000, entry-1) or ms == samples[-1][0]:
                    print(ms, [(r['position'], r['before'], r['after']) for r in rows])
        for errors in totals:
            if errors:
                print('all snapshots', len(errors), 'rank MAE', round(mean(e for e, _ in errors), 2),
                      'pair hits', sum(hit for _, hit in errors))


if __name__ == '__main__':
    compare(Path(sys.argv[1]))
