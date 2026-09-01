#!/usr/bin/env python3
"""Persist the battery workflow output (arg1 = task .output path) into per-phase JSON files keyed by task_id."""
import json, sys, os
RUN = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(sys.argv[1]))
d = d['result'] if isinstance(d, dict) and 'result' in d else d
files = {'parity':'phase2_parity.json','uk':'phase2_uk.json','ratings':'phase_ratings.json',
         'justif':'phase3b_justif.json','evidence':'phase_evidence.json','persona':'phase_persona.json',
         'misc':'phase_misc.json','progdisc':'phase_progdisc.json','low_effort':'phase_lowffort.json'}
allids = set(json.load(open(f'{RUN}/pending_ids.json')))
def key(r): return r.get('task_id') or r.get('tid')
for phase, fn in files.items():
    recs = d.get(phase) or []
    m = {}
    for r in recs:
        if not isinstance(r, dict): continue
        k = key(r)
        if phase == 'parity' and isinstance(r.get('parity'), dict):
            m[k] = r['parity']
        else:
            m[k] = r
    json.dump(m, open(f'{RUN}/{fn}', 'w'), indent=1, ensure_ascii=False)
    missing = allids - set(m.keys())
    print(f'{fn}: {len(m)}' + (f'  MISSING {len(missing)}: {sorted(missing)}' if missing else ''))
