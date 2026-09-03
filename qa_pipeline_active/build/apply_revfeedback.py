#!/usr/bin/env python3
"""L10 only: apply qa_active_revfeedback.js verdicts to the L10 categories.

CLEARED               -> category 'no issues'  (needs-review drivers were stale/resolved)
DOWNGRADE_TO_BACKFILL -> category 'backfill'   (residual_backfill drivers kept)
STILL_NEEDS_REVIEW    -> unchanged

Rewrites deliverables/eval_findings.csv in place (keeping a .prerevfb backup), records the
adjudication in revfeedback/revfeedback_verdicts.json, and refreshes worklist.json entries
for any task that became a backfill.

usage: apply_revfeedback.py <revfeedback.output>
"""
import csv, json, os, re, shutil, sys

RUN = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) < 2:
    sys.exit('usage: apply_revfeedback.py <revfeedback.output>')

raw = json.load(open(sys.argv[1]))
recs = raw.get('result', raw) if isinstance(raw, dict) else raw
if isinstance(recs, dict):
    recs = recs.get('result', list(recs.values()))
verdicts = {r['task_id']: r for r in recs if isinstance(r, dict) and r.get('task_id')}
print(f'[revfeedback] {len(verdicts)} verdict(s) loaded')

EF = os.path.join(RUN, 'deliverables', 'eval_findings.csv')
shutil.copy2(EF, EF + '.prerevfb')
with open(EF) as f:
    rd = csv.DictReader(f); cols = rd.fieldnames; rows = list(rd)

BACK = {'ratings', 'justif', 'citation', 'gating', 'uk_in_justification', 'persona', 'low_effort'}
NEEDS = {'parity', 'no_valid_stump', 'uk_in_session', 'meta_leak', 'not_healthcare', 'structural', 'wrong_pdf'}
VOCAB = BACK | NEEDS


def norm(ds):
    """The eval sometimes annotates a driver ('parity (conversation-level: ...)'). Keep only the
    leading token so downstream token matching cannot silently miss a cleared driver."""
    out = []
    for d in ds or []:
        tok = re.split(r'[^a-z_]', (d or '').strip().lower(), 1)[0]
        if tok in VOCAB and tok not in out:
            out.append(tok)
    return out
changed = {'CLEARED': [], 'DOWNGRADE_TO_BACKFILL': [], 'STILL_NEEDS_REVIEW': []}
for r in rows:
    v = verdicts.get(r['task_id'])
    if not v or r['level'] != 'L10':
        continue
    verdict = v['verdict']
    changed[verdict].append(r['task_id'])
    if verdict == 'STILL_NEEDS_REVIEW':
        # category is unchanged, but a driver the reviewer REFUTED must not survive into the
        # feedback we hand back — otherwise we tell the reviewer "no valid stump" on a task
        # where we just accepted their stump.
        # a driver named in BOTH lists is only PARTIALLY cleared (the eval split it into a
        # resolved and an unresolved sub-claim) — standing wins, keep the driver.
        drop = set(norm(v.get('drivers_cleared'))) - set(norm(v.get('drivers_standing')))
        if drop:
            r['drivers'] = ','.join([d for d in r['drivers'].split(',') if d and d not in drop])
        continue
    standing = norm(v.get('drivers_standing'))
    keep = [d for d in r['drivers'].split(',') if d and d in standing]
    keep += [d for d in norm(v.get('residual_backfill')) if d in BACK and d not in keep]
    if verdict == 'DOWNGRADE_TO_BACKFILL':
        keep = [d for d in keep if d in BACK] or ['ratings']
        r['category'] = 'backfill'
    else:  # CLEARED
        keep = [d for d in keep if d in BACK]
        r['category'] = 'backfill' if keep else 'no issues'
    r['drivers'] = ','.join(keep)

with open(EF, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow(r)

OUT = os.path.join(RUN, 'revfeedback')
json.dump(verdicts, open(os.path.join(OUT, 'revfeedback_verdicts.json'), 'w'), indent=1, ensure_ascii=False)

# Drivers the reviewer pass CLEARED. build_worklist.py must honour these: a cleared driver's
# finding was refuted, so it must not come back as a justification rewrite / score correction
# regenerated from the (now stale) phase files.
cleared = {}
for t, v in verdicts.items():
    c = [d for d in norm(v.get('drivers_cleared')) if d not in norm(v.get('drivers_standing'))]
    if c:
        cleared[t] = c
json.dump(cleared, open(os.path.join(OUT, 'cleared_drivers.json'), 'w'), indent=1, ensure_ascii=False)
print('  cleared drivers ->', {t[-6:]: v for t, v in cleared.items()})

# drop worklist entries for tasks that ended up with no backfill work
wl_path = os.path.join(RUN, 'worklist.json')
if os.path.exists(wl_path):
    wl = json.load(open(wl_path))
    cats = {r['task_id']: r['category'] for r in rows}
    for t in list(wl):
        if cats.get(t) == 'no issues':
            wl.pop(t)
    json.dump(wl, open(wl_path, 'w'), indent=1, ensure_ascii=False)

for k, v in changed.items():
    print(f'  {k}: {len(v)}')
align = {}
for v in verdicts.values():
    align[v.get('reviewer_alignment', '?')] = align.get(v.get('reviewer_alignment', '?'), 0) + 1
print('  reviewer alignment:', align)
