#!/usr/bin/env python3
"""Build meta.json (per-task level/form_type/country/provider-order/persona/links/turns) from the CSV + turns_summary."""
import csv, json, os, sys
from collections import defaultdict
RUN = os.path.dirname(os.path.abspath(__file__))
# input CSV: 1st CLI arg, else $QA_INPUT_CSV, else meta.json's recorded source
CSV = (sys.argv[1] if len(sys.argv) > 1 else None) or os.environ.get("QA_INPUT_CSV")
if not CSV:
    sys.exit("build_meta: pass the V19 input CSV as arg1 or set QA_INPUT_CSV")
rows = list(csv.DictReader(open(CSV)))
by = defaultdict(list)
for r in rows: by[r['task id']].append(r)
ids = json.load(open(f'{RUN}/pending_ids.json'))
ts = json.load(open(f'{RUN}/turns_summary.json'))
def form_of(tax):
    t = (tax or '').upper()
    return 'Form A' if 'FORM A' in t else 'Form B' if 'FORM B' in t else 'Form C' if 'FORM C' in t else ''
meta = {}
for t in ids:
    rs = by[t]; r0 = rs[0]
    provrows = sorted([r for r in rs if (r.get('provider') or '').strip()],
                      key=lambda r: int((r.get('provider #') or '99').strip() or 99))
    turns = ts.get(t, {}).get('turns', {})
    meta[t] = {
        'task_id': t, 'level': r0['level'].strip(), 'form_type': form_of(r0.get('taxonomy', '')),
        'attempt_id': r0.get('attempt id', '').strip(), 'attempter': r0.get('submitted by', '').strip(),
        'country': (r0.get('country') or '').strip(), 'persona': (r0.get('persona') or '').strip(),
        'modality': (r0.get('modality') or '').strip(), 'task_category': (r0.get('task category') or '').strip(),
        'specializations': (r0.get('specializations') or '').strip(),
        'provider_order': [(r.get('provider') or '').strip().lower() for r in provrows],
        'links': {(r.get('provider') or '').strip().lower(): (r.get('session link') or '').strip() for r in provrows},
        'turns': turns, 'min_turns': min(turns.values()) if turns else 0,
    }
json.dump(meta, open(f'{RUN}/meta.json', 'w'), indent=1, ensure_ascii=False)
print('meta.json written for', len(meta), 'tasks')
