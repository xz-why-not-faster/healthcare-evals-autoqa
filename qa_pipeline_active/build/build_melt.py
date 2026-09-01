#!/usr/bin/env python3
"""Emit the backfill deliverable in LONG format: columns task, step, value.
One row per changed field (each rewritten dim -> a rating row + a justification row),
step = the form-specific step field id, value = the corrected score / revoiced justification."""
import csv, json, os
RUN = os.path.dirname(os.path.abspath(__file__))
meta = json.load(open(f'{RUN}/meta.json'))
worklist = json.load(open(f'{RUN}/worklist.json'))
BF = json.load(open(f'{RUN}/phase_backfill.json')) if os.path.exists(f'{RUN}/phase_backfill.json') else {}
persona_eval = json.load(open(f'{RUN}/phase_persona.json'))
findings = {r['task_id']: r for r in csv.DictReader(open(f'{RUN}/deliverables/eval_findings.csv'))}

def persona_cols(name):
    n = (name or '').lower()
    if 'acute' in n:     return ('acute_care', 'Acute Care', 'Immediate, high-intent clarity during active health events.')
    if 'frontier' in n:  return ('frontier_health', 'Frontier Health', 'Deep, ongoing tracking for prosumers optimizing their health or tracking long-term outcomes.')
    if 'lifestyle' in n: return ('lifestyle', 'Lifestyle', 'Coaching and planning for ongoing lifestyle goals.')
    return ('', name or '', '')

# dim key -> form field base (Form C and Form B share these bases; suffix _N added per slot/provider)
FIELD = {'overall':'overall_rating','clinical_accuracy':'clinical_accuracy','safety_triage':'safety_triage',
         'completeness':'completeness_quality','communication_tone':'communication_tone',
         'instruction_following':'instruction_following','interaction_efficiency':'interaction_efficiency',
         'multimodal_fidelity':'multimodal_fidelity','personal_context':'personal_context',
         'ui_experience':'ui_experience','worth_using_again':'worth_using_again'}
# Form C: step id + numeric suffix keyed by PROVIDER identity
FORMC = {'chatgpt':('step-ResponseTextCollection-e5e516fcaeda',1),
         'claude':('step-ResponseTextCollection-d3fb717a6196',2),
         'gemini':('step-ResponseTextCollection-b0eeaf40bd9a',3)}
# Form B: step id + numeric suffix keyed by SLOT (provider order position)
FORMB_SLOT = {1:'step-TextCollection-970d11e30964',2:'step-TextCollection-1d5d1f26cd9c',3:'step-TextCollection-084a3c17e83d'}

def step_ids(task, prov):
    """Return (rating_step, just_step) for a given task+provider, per its form."""
    m = meta[task]; form = m.get('form_type','')
    return None  # placeholder (unused)

rows = []
for t, wl in worklist.items():
    m = meta.get(t, {}); form = m.get('form_type', '')
    order = m.get('provider_order') or ['chatgpt','claude','gemini']
    bfp = (BF.get(t, {}) or {}).get('providers', {})
    for prov, pd in wl['providers'].items():
        for dim, fx in pd['fixes'].items():
            if not fx.get('needs_rewrite'): continue
            base = FIELD.get(dim)
            if not base: continue
            # resolve step id + suffix
            if form == 'Form B':
                try: n = order.index(prov) + 1
                except ValueError: continue
                stepid = FORMB_SLOT.get(n)
            else:  # Form C (default)
                if prov not in FORMC: continue
                stepid, n = FORMC[prov]
            if not stepid: continue
            # values: prefer the (revoiced) phase_backfill entry; fall back to worklist target
            bj = ((bfp.get(prov, {}) or {}).get(dim, {}) or {})
            score = bj.get('score', fx.get('target_score'))
            just = bj.get('justification', '')
            rows.append({'task': t, 'step': f'{stepid}.{base}_{n}', 'value': score})
            rows.append({'task': t, 'step': f'{stepid}.{base}_just_{n}', 'value': just})

# ---- persona corrections now live in the separate persona_updates.csv (build_persona_sheet.py) ----
# Disabled here to avoid duplicating persona metadata rows across two deliverables.
persona_rows = 0

with open(f'{RUN}/deliverables/backfill_melt.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['task','step','value']); w.writeheader()
    for r in rows: w.writerow(r)
print('melt rows:', len(rows), '| persona metadata rows:', persona_rows, '| tasks:', len({r["task"] for r in rows}))
