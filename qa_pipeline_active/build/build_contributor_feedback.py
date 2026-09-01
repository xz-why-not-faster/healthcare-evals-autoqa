#!/usr/bin/env python3
"""Emit contributor_feedback.csv for needs-review tasks whose needs-drivers are EXCLUSIVELY
parity and/or structural (broken link). Uses the plain-language, reviewer-facing prose produced
by qa_active_external.js (phase_external.json) — the same cleaned bullets that feed external_feedback
— so the contributor gets clear "what to fix" language: the specific parity break, the specific
broken link, plus a little feedback on their scores/justifications. Also writes
contributor_feedback_ids.json so build_sheets excludes these from external_feedback.csv."""
import csv, json, os, re

RUN = os.path.dirname(os.path.abspath(__file__))
NEEDS = {'parity', 'uk_in_session', 'no_valid_stump', 'meta_leak', 'not_healthcare', 'structural'}

findings = {r['task_id']: r for r in csv.DictReader(open(f'{RUN}/deliverables/eval_findings.csv'))}
_ep = os.path.join(RUN, 'phase_external.json')
EXT = json.load(open(_ep)) if os.path.exists(_ep) else {}

def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()

rows = []
selected = []
for t, r in findings.items():
    if r['category'] != 'needs review':
        continue
    drivers = {d.strip() for d in (r.get('drivers', '') or '').split(',')}
    nd = drivers & NEEDS
    # contributor feedback ONLY when the needs-drivers are exclusively parity and/or structural
    if not nd or not (nd <= {'parity', 'structural'}):
        continue
    selected.append(t)
    e = EXT.get(t, {})
    # clean reviewer-facing prose: the parity/broken-link fix (session) + any task-level misc.
    # Deliberately EXCLUDE the ratings/justification notes (rate) from contributor feedback.
    parts = [clean(e.get('session', '')), clean(e.get('misc', ''))]
    fb = '  '.join(p for p in parts if p and p.lower() not in ('n/a', 'none', ''))
    if not fb:
        fb = clean(r.get('parity', '')) or 'Needs review for a parity/structural issue.'
    rows.append({'task_id': t, 'contributor feedback': fb})

with open(f'{RUN}/deliverables/contributor_feedback.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['task_id', 'contributor feedback'])
    w.writeheader()
    for r in rows:
        w.writerow(r)
json.dump(selected, open(f'{RUN}/contributor_feedback_ids.json', 'w'))
print(f'contributor_feedback.csv: {len(rows)} tasks (clean reviewer-facing prose from phase_external)')
