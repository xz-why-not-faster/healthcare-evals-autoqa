#!/usr/bin/env python3
"""Build external_input/<tid>.json for the run's needs-review tasks from eval_findings.
Maps findings -> {category, session_errors, artifact_upload_errors, rating_errors, misc_errors}.
Review level comes from $QA_LEVEL (default L1)."""
import csv, json, os
RUN = os.path.dirname(os.path.abspath(__file__))
LEVEL = os.environ.get('QA_LEVEL', 'L1')
os.makedirs(os.path.join(RUN, 'external_input'), exist_ok=True)
rows = [r for r in csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv')))
        if r['level'] == LEVEL and r['category'] == 'needs review']

def j(*parts):
    parts = [p.strip() for p in parts if p and p.strip()]
    return ' ;; '.join(parts)


# Each findings COLUMN is owned by a driver. A driver that was dropped (e.g. refuted by the L10
# reviewer-feedback pass) must not leak its column text into reviewer-facing feedback — otherwise
# we hand back "no model stumps here" on a task whose stump we just accepted.
COL_DRIVER = {
    'parity': 'parity', 'structural': 'structural', 'uk_in_session': 'uk_in_session',
    'ratings_disagreements': 'ratings', 'justif_inconsistencies': 'justif',
    'evidence_needed': 'citation', 'gating_violations': 'gating',
    'uk_in_justification': 'uk_in_justification', 'stump_validity': 'no_valid_stump',
    'meta_leak': 'meta_leak', 'not_healthcare': 'not_healthcare',
    'persona_mismatch': 'persona', 'artifact_errors': 'wrong_pdf',
}


def live(r, col):
    """Column text, but only if the driver that owns it is still in this task's driver list."""
    drv = COL_DRIVER.get(col)
    if drv and drv not in {d.strip() for d in (r.get('drivers') or '').split(',') if d.strip()}:
        return ''
    return r.get(col, '') or ''

n = 0
for r in rows:
    session = j(
        (('PARITY: ' + live(r, 'parity')) if live(r, 'parity').startswith('FAIL') else ''),
        (('STRUCTURAL: ' + live(r, 'structural')) if live(r, 'structural') else ''),
        (('UK IN SESSION: ' + live(r, 'uk_in_session')) if live(r, 'uk_in_session') else ''),
    )
    rating = j(
        (('RATINGS DISAGREEMENT: ' + live(r, 'ratings_disagreements')) if live(r, 'ratings_disagreements') else ''),
        (('JUSTIFICATION INCONSISTENCY: ' + live(r, 'justif_inconsistencies')) if live(r, 'justif_inconsistencies') else ''),
        (('CITATION NEEDED: ' + live(r, 'evidence_needed')) if live(r, 'evidence_needed') else ''),
        (('GATING: ' + live(r, 'gating_violations')) if live(r, 'gating_violations') else ''),
        (('UK IN JUSTIFICATION: ' + live(r, 'uk_in_justification')) if live(r, 'uk_in_justification') else ''),
    )
    misc = j(
        (('NO VALID STUMP: ' + live(r, 'stump_validity').split(':', 1)[-1]) if live(r, 'stump_validity').startswith('NO_VALID_STUMP') else ''),
        (('META LEAK: ' + live(r, 'meta_leak')) if live(r, 'meta_leak') else ''),
        (('NOT HEALTHCARE: ' + live(r, 'not_healthcare')) if live(r, 'not_healthcare') else ''),
        (('PERSONA MISMATCH: ' + live(r, 'persona_mismatch')) if live(r, 'persona_mismatch') else ''),
    )
    obj = {'task_id': r['task_id'], 'category': r['category'],
           'session_errors': session or '', 'artifact_upload_errors': live(r, 'artifact_errors'),
           'rating_errors': rating or '', 'misc_errors': misc or ''}
    json.dump(obj, open(os.path.join(RUN, 'external_input', f'{r["task_id"]}.json'), 'w'), indent=1, ensure_ascii=False)
    n += 1
print('external_input written for', n, LEVEL, 'needs-review tasks')
