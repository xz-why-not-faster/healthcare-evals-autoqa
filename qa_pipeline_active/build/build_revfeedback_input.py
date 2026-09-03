#!/usr/bin/env python3
"""L10 only: build revfeedback/<tid>.json for every needs-review task.

Pairs our eval_findings row with the human review feedback written on the task in the
V19 "review data" export (L0 reviewer notes, agree/disagree flags, the fixes they made,
QC score/feedback, and any prior auto-feedback they were responding to).
Consumed by evals/qa_active_revfeedback.js.

usage: build_revfeedback_input.py <review_data.csv> [--all]
"""
import csv, json, os, sys

RUN = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith('--')]
ALL = '--all' in sys.argv
CSV = (args[0] if args else None) or os.environ.get('QA_REVIEW_CSV')
if not CSV:
    sys.exit('build_revfeedback_input: pass the V19 review-data CSV as arg1 or set QA_REVIEW_CSV')

findings = list(csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv'))))
rev = {r['task id']: r for r in csv.DictReader(open(CSV))}

def g(r, k):
    return (r.get(k) or '').strip()

OUT = os.path.join(RUN, 'revfeedback')
os.makedirs(OUT, exist_ok=True)
ids, missing = [], []
for f in findings:
    if f['level'] != 'L10':
        continue
    if not ALL and f['category'] != 'needs review':
        continue
    t = f['task_id']
    r = rev.get(t)
    if not r:
        missing.append(t)
        continue
    rec = {
        'task_id': t,
        'form_type': f['form_type'],
        'our_category': f['category'],
        'our_drivers': [d for d in f['drivers'].split(',') if d],
        'our_findings': {k: v for k, v in f.items() if v and k not in ('task_id', 'level')},
        # combined V19 CSV: reviewer columns are L0-prefixed; attempter is 'submitted by'
        'reviewer': {
            'l0_reviewer': g(r, 'L0 reviewer'),
            'l0_review_pt': g(r, 'L0 review (pt)'),
            'attempter': g(r, 'submitted by'),
            'reviewer_disagreed': g(r, 'L0 reviewer disagreed'),
            'can_fix_task': g(r, 'L0 can fix task'),
            'task_ready': g(r, 'L0 task ready'),
            'qc_score': g(r, 'L0 QC score'),
            'qc_feedback': g(r, 'L0 QC feedback'),
            'agree': {
                'ratings_errors': g(r, 'L0 agree ratings errors'),
                'session_errors': g(r, 'L0 agree session errors'),
                'artifact_errors': g(r, 'L0 agree artifact errors'),
                'misc_errors': g(r, 'L0 agree misc errors'),
            },
            'notes': {
                'ratings_errors': g(r, 'L0 ratings errors notes'),
                'session_errors': g(r, 'L0 session errors notes'),
                'artifact_errors': g(r, 'L0 artifact errors notes'),
                'misc_errors': g(r, 'L0 misc errors notes'),
                'additional': g(r, 'L0 additional notes'),
            },
            'fixes': {
                'ratings_errors': g(r, 'L0 fix ratings errors'),
                'session_errors': g(r, 'L0 fix session errors'),
                'artifact_errors': g(r, 'L0 fix artifact errors'),
                'misc_errors': g(r, 'L0 fix misc errors'),
            },
            'prior_auto_feedback': {
                'rate': g(r, 'L0 auto rate_feedback'),
                'session': g(r, 'L0 auto session_feedback'),
                'artifact': g(r, 'L0 auto artifact_feedback'),
                'misc': g(r, 'L0 auto misc_feedback'),
            },
            'prior_sandbox_eval': {
                'ran_sandbox': g(r, 'ran sandbox'),
                'audit': g(r, 'eval transcripts'),
                'ratings_audit': g(r, 'eval ratings audit'),
                'broken_transcripts': g(r, 'broken transcripts'),
                'cb_response_to_eval': g(r, 'response to eval'),
            },
        },
    }
    json.dump(rec, open(os.path.join(OUT, f'{t}.json'), 'w'), indent=1, ensure_ascii=False)
    ids.append(t)

json.dump(ids, open(os.path.join(OUT, 'revfeedback_ids.json'), 'w'), indent=1)
print(f'revfeedback input written for {len(ids)} L10 task(s) -> revfeedback/')
if missing:
    print(f'  WARNING: no review-data row for {len(missing)} task(s): {missing}')
