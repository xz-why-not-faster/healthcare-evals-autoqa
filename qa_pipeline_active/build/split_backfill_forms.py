#!/usr/bin/env python3
"""Split backfill_forms.csv into Form C and Form B sheets, each with a TWO-ROW header:
row 1 = step field IDs (for p*_generated_upload onward; 'metadata' over persona block; blank elsewhere),
row 2 = original column names. Form B and Form C have DIFFERENT step IDs + field layouts."""
import csv, os
RUN = os.path.dirname(os.path.abspath(__file__))
DL = os.path.join(RUN, 'deliverables')
rows = list(csv.DictReader(open(os.path.join(DL, 'backfill_forms.csv'))))
cols = list(rows[0].keys())
METADATA = {'persona', 'persona_name', 'persona_description'}

# ---- Form C template (fields suffixed by provider identity: chatgpt=_1, claude=_2, gemini=_3) ----
FORMC = {
    'resp': {1: 'step-ResponseTextCollection-e5e516fcaeda',
             2: 'step-ResponseTextCollection-d3fb717a6196',
             3: 'step-ResponseTextCollection-b0eeaf40bd9a'},
    'gen_step': 'step-TextCollection-826f5678a3ef',
    'gen_field': {1: 'chatgpt_generated_files', 2: 'claude_generated_files', 3: 'gemini_generated_files'},
    'gen_same_step_as_resp': False,
    'dim': {'overall_rating': 'overall_rating', 'overall_justification': 'overall_rating_just',
            'clinical_rating': 'clinical_accuracy', 'clinical_justification': 'clinical_accuracy_just',
            'triage_rating': 'safety_triage', 'triage_justification': 'safety_triage_just'},
}
# ---- Form B template (fields suffixed by SLOT: slot1=_1, slot2=_2, slot3=_3; gen = session_artifacts_N in same slot step) ----
FORMB = {
    'resp': {1: 'step-TextCollection-970d11e30964',
             2: 'step-TextCollection-1d5d1f26cd9c',
             3: 'step-TextCollection-084a3c17e83d'},
    'gen_field': {1: 'session_artifacts_1', 2: 'session_artifacts_2', 3: 'session_artifacts_3'},
    'gen_same_step_as_resp': True,
    'dim': {'overall_rating': 'overall_rating', 'overall_justification': 'overall_rating_just',
            'clinical_rating': 'clinical_accuracy', 'clinical_justification': 'clinical_accuracy_just',
            'triage_rating': 'safety_triage', 'triage_justification': 'safety_triage_just'},
}

def step_header(col, cfg):
    if col in METADATA:
        return 'metadata'
    if col.startswith('p') and '_' in col:
        try:
            n = int(col[1])
        except (ValueError, IndexError):
            return ''
        rest = col[3:]
        if rest == 'generated_upload':
            if cfg['gen_same_step_as_resp']:
                return f"{cfg['resp'][n]}.{cfg['gen_field'][n]}"
            return f"{cfg['gen_step']}.{cfg['gen_field'][n]}"
        if rest in cfg['dim']:
            return f"{cfg['resp'][n]}.{cfg['dim'][rest]}_{n}"
    return ''

def write_sheet(form, cfg, out):
    sub = [r for r in rows if r['form_type'] == form]
    if not sub:
        print(f'{form}: 0 rows, skipped'); return
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([step_header(c, cfg) for c in cols])
        w.writerow(cols)
        for r in sub:
            w.writerow([r.get(c, '') for c in cols])
    print(f'{form}: {len(sub)} rows -> {os.path.basename(out)}')

write_sheet('Form C', FORMC, os.path.join(DL, 'backfill_forms_formC.csv'))
write_sheet('Form B', FORMB, os.path.join(DL, 'backfill_forms_formB.csv'))
