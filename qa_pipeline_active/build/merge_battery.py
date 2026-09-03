#!/usr/bin/env python3
"""Merge two or more battery .output files into one, per phase, keyed by task id.

A network outage kills whichever agents are in flight, so a re-run typically has holes in a
DIFFERENT eval than the original. Merging the runs usually reaches full coverage without
another resume. Later files win on conflict; records with a null payload never overwrite a
real one.

usage: merge_battery.py <out.json> <battery1.output> <battery2.output> [...]
"""
import json, os, sys

if len(sys.argv) < 4:
    sys.exit(__doc__)
RUN = os.path.dirname(os.path.abspath(__file__))
dest, srcs = sys.argv[1], sys.argv[2:]
ids = set(json.load(open(os.path.join(RUN, 'pending_ids.json'))))
PHASES = ['parity', 'ratings', 'justif', 'evidence', 'low_effort', 'uk', 'misc', 'persona', 'progdisc']


def payload_ok(phase, rec):
    """parity records arrive as {tid, parity:{...}}; a failed agent leaves parity=None."""
    if phase == 'parity':
        return rec.get('parity') is not None
    return True


merged = {ph: {} for ph in PHASES}
for src in srcs:
    d = json.load(open(src))
    d = d.get('result', d) if isinstance(d, dict) else d
    for ph in PHASES:
        for rec in (d.get(ph) or []):
            if not isinstance(rec, dict):
                continue
            k = rec.get('task_id') or rec.get('tid')
            if k not in ids or not payload_ok(ph, rec):
                continue
            merged[ph][k] = rec

out = {ph: list(v.values()) for ph, v in merged.items()}
json.dump(out, open(dest, 'w'), ensure_ascii=False)
print(f'merged {len(srcs)} run(s) -> {os.path.basename(dest)}')
total = 0
for ph in PHASES:
    n = len(merged[ph]); total += n
    print(f'  {ph:<12}{n}/{len(ids)}' + ('' if n == len(ids) else f'   MISSING {sorted(x[-6:] for x in ids - set(merged[ph]))}'))
print(f'coverage: {total}/{len(ids)*len(PHASES)}')
