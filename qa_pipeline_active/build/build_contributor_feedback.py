#!/usr/bin/env python3
"""Emit contributor_feedback.csv — the ATTEMPTER pool of needs-review tasks.

ROUTING (a needs-review task falls to its HIGHEST-TOUCH driver):
  - REVIEWER (high touch) — {no_valid_stump, uk_in_session, not_healthcare}. If a task has ANY of
    these it goes to the reviewer (external_feedback.csv), even if it also has attempter-fixable
    issues. These need reviewer judgment / re-collection, not just the attempter redoing the task.
  - ATTEMPTER (lower touch) — everything else that's needs-review: parity, a short/broken session
    (structural), a wrong-PDF upload, and a user meta-instruction leak (meta_leak). A task whose
    needs-drivers are ONLY these goes back to the original attempter, here.

Uses the plain-language prose from qa_active_external.js (phase_external.json) so the attempter gets
clear "what to fix" language. Also writes contributor_feedback_ids.json so build_sheets excludes
these from external_feedback.csv."""
import csv, json, os, re

RUN = os.path.dirname(os.path.abspath(__file__))
NEEDS = {'parity', 'uk_in_session', 'no_valid_stump', 'meta_leak', 'not_healthcare', 'structural', 'wrong_pdf'}
# High-touch drivers that force a task to the REVIEWER (external_feedback). Any of these present ->
# reviewer, regardless of what else the task has (highest-touch wins).
REVIEWER = {'no_valid_stump', 'uk_in_session', 'not_healthcare'}

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
    # highest-touch wins: any reviewer driver -> reviewer (skip here); only attempter-fixable -> here
    if not nd or (nd & REVIEWER):
        continue
    selected.append(t)
    e = EXT.get(t, {})
    # clean reviewer-facing prose: the parity/broken-link fix (session) + the wrong-PDF fix (artifact)
    # + any task-level misc. Deliberately EXCLUDE the ratings/justification notes (rate).
    parts = [clean(e.get('session', '')), clean(e.get('artifact', '')), clean(e.get('misc', ''))]
    fb = '  '.join(p for p in parts if p and p.lower() not in ('n/a', 'none', ''))
    if not fb:
        p = clean(r.get('parity', ''))
        fb = (p if p.upper().startswith('FAIL') else '') \
            or clean(r.get('artifact_errors', '')) \
            or 'Needs review for a parity, short-session, or uploaded-PDF issue.'
    rows.append({'task_id': t, 'contributor feedback': fb})

with open(f'{RUN}/deliverables/contributor_feedback.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['task_id', 'contributor feedback'])
    w.writeheader()
    for r in rows:
        w.writerow(r)
json.dump(selected, open(f'{RUN}/contributor_feedback_ids.json', 'w'))
print(f'contributor_feedback.csv: {len(rows)} tasks (clean reviewer-facing prose from phase_external)')
