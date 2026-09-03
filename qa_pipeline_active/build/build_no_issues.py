#!/usr/bin/env python3
"""Build deliverables/no_issues.csv — the tasks that passed every check, ready to approve.

They otherwise only exist as rows inside eval_findings.csv. Level comes from $QA_LEVEL
(default L1).
"""
import csv, json, os

RUN = os.path.dirname(os.path.abspath(__file__))
LEVEL = os.environ.get('QA_LEVEL', 'L1')
meta = json.load(open(os.path.join(RUN, 'meta.json')))
rows = [r for r in csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv')))
        if r['level'] == LEVEL and r['category'] == 'no issues']

COLS = ['task_id', 'level', 'form_type', 'attempter', 'country', 'persona', 'modality',
        'min_turns', 'turns_chatgpt', 'turns_claude', 'turns_gemini', 'verdict']
out = []
for r in rows:
    m = meta.get(r['task_id'], {}) or {}
    t = m.get('turns') or {}
    out.append({
        'task_id': r['task_id'], 'level': r['level'], 'form_type': r['form_type'],
        'attempter': m.get('attempter', ''), 'country': m.get('country', ''),
        'persona': m.get('persona', ''), 'modality': m.get('modality', ''),
        'min_turns': m.get('min_turns', ''),
        'turns_chatgpt': t.get('chatgpt', ''), 'turns_claude': t.get('claude', ''),
        'turns_gemini': t.get('gemini', ''),
        'verdict': 'no issues found — approve',
    })

path = os.path.join(RUN, 'deliverables', 'no_issues.csv')
with open(path, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
    for r in out: w.writerow(r)
print(f'no_issues.csv: {len(out)} {LEVEL} task(s) with no findings')
