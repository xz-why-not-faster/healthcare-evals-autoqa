#!/usr/bin/env python3
"""Build external_input/<tid>.json for L1 needs-review tasks from eval_findings.
Maps findings -> {category, session_errors, artifact_upload_errors, rating_errors, misc_errors}."""
import csv, json, os
RUN = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(RUN, 'external_input'), exist_ok=True)
rows = [r for r in csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv')))
        if r['level'] == 'L1' and r['category'] == 'needs review']

def j(*parts):
    parts = [p.strip() for p in parts if p and p.strip()]
    return ' ;; '.join(parts)

n = 0
for r in rows:
    session = j(
        (('PARITY: ' + r['parity']) if r['parity'].startswith('FAIL') else ''),
        (('STRUCTURAL: ' + r['structural']) if r['structural'] else ''),
        (('UK IN SESSION: ' + r['uk_in_session']) if r['uk_in_session'] else ''),
    )
    rating = j(
        (('RATINGS DISAGREEMENT: ' + r['ratings_disagreements']) if r['ratings_disagreements'] else ''),
        (('JUSTIFICATION INCONSISTENCY: ' + r['justif_inconsistencies']) if r['justif_inconsistencies'] else ''),
        (('CITATION NEEDED: ' + r['evidence_needed']) if r['evidence_needed'] else ''),
        (('GATING: ' + r['gating_violations']) if r['gating_violations'] else ''),
        (('UK IN JUSTIFICATION: ' + r['uk_in_justification']) if r['uk_in_justification'] else ''),
    )
    misc = j(
        (('NO VALID STUMP: ' + r['stump_validity'].split(':', 1)[-1]) if r['stump_validity'].startswith('NO_VALID_STUMP') else ''),
        (('META LEAK: ' + r['meta_leak']) if r['meta_leak'] else ''),
        (('NOT HEALTHCARE: ' + r['not_healthcare']) if r['not_healthcare'] else ''),
        (('PERSONA MISMATCH: ' + r['persona_mismatch']) if r['persona_mismatch'] else ''),
    )
    obj = {'task_id': r['task_id'], 'category': r['category'],
           'session_errors': session or '', 'artifact_upload_errors': (r.get('artifact_errors', '') or ''),
           'rating_errors': rating or '', 'misc_errors': misc or ''}
    json.dump(obj, open(os.path.join(RUN, 'external_input', f'{r["task_id"]}.json'), 'w'), indent=1, ensure_ascii=False)
    n += 1
print('external_input written for', n, 'L1 needs-review tasks')
