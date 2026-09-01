#!/usr/bin/env python3
"""Persist ONLY ratings + justif from a re-run workflow output (arg1 = task .output path).
Leaves all other phase files untouched (unlike persist_battery which rewrites every phase)."""
import json, sys, os
RUN = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(sys.argv[1]))
d = d['result'] if isinstance(d, dict) and 'result' in d else d
files = {'ratings': 'phase_ratings.json', 'justif': 'phase3b_justif.json'}
allids = set(json.load(open(f'{RUN}/pending_ids.json')))
def key(r): return r.get('task_id') or r.get('tid')
for phase, fn in files.items():
    recs = d.get(phase) or []
    if not recs:
        print(f'{fn}: NO RECORDS in output — NOT overwriting existing file')
        continue
    m = {}
    for r in recs:
        if isinstance(r, dict) and key(r):
            m[key(r)] = r
    json.dump(m, open(f'{RUN}/{fn}', 'w'), indent=1, ensure_ascii=False)
    missing = allids - set(m.keys())
    print(f'{fn}: {len(m)}' + (f'  MISSING {len(missing)}: {sorted(missing)}' if missing else ''))
