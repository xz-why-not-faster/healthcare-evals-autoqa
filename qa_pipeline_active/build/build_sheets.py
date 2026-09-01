#!/usr/bin/env python3
"""Build L1 deliverables: external_feedback.csv + backfill_forms.csv.
eval_findings.csv is already emitted by categorize.py (filter to L1 here too)."""
import csv, json, os, sys
RUN = os.path.dirname(os.path.abspath(__file__))
WS  = os.path.join(RUN, '..', 'workspace')
# input CSV: 1st CLI arg, else $QA_INPUT_CSV
CSV = (sys.argv[1] if len(sys.argv) > 1 else None) or os.environ.get("QA_INPUT_CSV")
if not CSV:
    sys.exit("build_sheets: pass the V19 input CSV as arg1 or set QA_INPUT_CSV")

meta = json.load(open(os.path.join(RUN, 'meta.json')))
findings = [r for r in csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv'))) if r['level'] == 'L1']
fmap = {r['task_id']: r for r in findings}
worklist = json.load(open(os.path.join(RUN, 'worklist.json')))
BF = json.load(open(os.path.join(RUN, 'phase_backfill.json'))) if os.path.exists(os.path.join(RUN, 'phase_backfill.json')) else {}
EXT = json.load(open(os.path.join(RUN, 'phase_external.json'))) if os.path.exists(os.path.join(RUN, 'phase_external.json')) else {}
persona_eval = json.load(open(os.path.join(RUN, 'phase_persona.json')))

# produced artifacts per (task, provider)
prod = {}
for r in csv.DictReader(open(CSV)):
    prov = (r.get('provider') or '').strip().lower()
    if not prov: continue
    prod[(r['task id'], prov)] = (r.get('produced artifacts') or '').strip()

def gen_cell(t, prov):
    v = prod.get((t, prov), '')
    if not v: return '[]'
    try:
        arr = json.loads(v)
        return json.dumps(arr, ensure_ascii=False) if arr else '[]'
    except Exception:
        return v or '[]'

def persona_cols(name):
    n = (name or '').lower()
    if 'acute' in n:     return ('acute_care', 'Acute Care', 'Immediate, high-intent clarity during active health events.')
    if 'frontier' in n:  return ('frontier_health', 'Frontier Health', 'Deep, ongoing tracking for prosumers optimizing their health or tracking long-term outcomes.')
    if 'lifestyle' in n: return ('lifestyle', 'Lifestyle', 'Coaching and planning for ongoing lifestyle goals.')
    return ('', name or '', '')

def ws_ratings(t):
    c = json.load(open(os.path.join(WS, f'task_{t}.json')))
    return {p: (pd.get('ratings') or {}) for p, pd in (c.get('providers') or {}).items() if isinstance(pd, dict)}

# ---------- external_feedback.csv (L1 needs-review) ----------
EXT_COLS = ['task_id','form_type','level','category','session_errors_external','artifact_upload_errors_external',
            'rate_justification_errors_external','misc_errors_external',
            'chatgpt_session_link','claude_session_link','gemini_session_link']
def na(x): return x.strip() if x and x.strip() else 'n/a'
# tasks moved to the separate contributor_feedback.csv (parity/structural needs-review) are excluded here
import os as _os
_cf = _os.path.join(RUN, 'contributor_feedback_ids.json')
CONTRIB_FB = set(json.load(open(_cf))) if _os.path.exists(_cf) else set()
ext_rows = []
for r in findings:
    if r['category'] != 'needs review': continue
    t = r['task_id']
    if t in CONTRIB_FB: continue
    e = EXT.get(t, {})
    links = meta[t].get('links', {})
    ext_rows.append({
        'task_id': t, 'form_type': r['form_type'], 'level': 'L1', 'category': 'needs review',
        'session_errors_external': na(e.get('session', '')), 'artifact_upload_errors_external': na(e.get('artifact', '')),
        'rate_justification_errors_external': na(e.get('rate', '')), 'misc_errors_external': na(e.get('misc', '')),
        'chatgpt_session_link': links.get('chatgpt', ''), 'claude_session_link': links.get('claude', ''),
        'gemini_session_link': links.get('gemini', ''),
    })
with open(os.path.join(RUN, 'deliverables', 'external_feedback.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=EXT_COLS); w.writeheader()
    for r in ext_rows: w.writerow(r)

# ---------- backfill_forms.csv (L1 backfill) ----------
DIMKEYS = [('overall','overall'), ('clinical','clinical_accuracy'), ('triage','safety_triage')]
base = ['form','review_level','form_type','task_id','main_action','provider_1','provider_2','provider_3',
        'chatgpt_session_link','claude_session_link','gemini_session_link',
        'original_persona','persona','persona_name','persona_description','ratings_qc_flag']
per = []
for n in (1,2,3):
    per += [f'p{n}_generated_upload', f'p{n}_overall_rating', f'p{n}_overall_justification',
            f'p{n}_clinical_rating', f'p{n}_clinical_justification', f'p{n}_triage_rating', f'p{n}_triage_justification']
BF_COLS = base + per

bf_rows = []
for r in findings:
    if r['category'] != 'backfill': continue
    t = r['task_id']; m = meta[t]
    porder = m.get('provider_order') or ['chatgpt','claude','gemini']
    wr = ws_ratings(t)
    wl = worklist.get(t, {}).get('providers', {})
    bfd = BF.get(t, {}).get('providers', {}) if isinstance(BF.get(t), dict) else {}
    pe = persona_eval.get(t, {})
    orig_persona = m.get('persona', '')
    corrected = pe.get('suggested_persona') if (pe and not pe.get('fits_assigned_persona', True)) else orig_persona
    pslug, pname, pdesc = persona_cols(corrected)
    row = {
        'form': 'backfill', 'review_level': 'L1', 'form_type': r['form_type'], 'task_id': t,
        'main_action': 'backfill',
        'provider_1': porder[0] if len(porder) > 0 else '', 'provider_2': porder[1] if len(porder) > 1 else '',
        'provider_3': porder[2] if len(porder) > 2 else '',
        'chatgpt_session_link': m['links'].get('chatgpt', ''), 'claude_session_link': m['links'].get('claude', ''),
        'gemini_session_link': m['links'].get('gemini', ''),
        'original_persona': orig_persona, 'persona': pslug, 'persona_name': pname, 'persona_description': pdesc,
        'ratings_qc_flag': 'yes' if (r['ratings_disagreements'] or r['gating_violations']) else '',
    }
    for i, prov in enumerate(porder[:3], start=1):
        row[f'p{i}_generated_upload'] = gen_cell(t, prov)
        wrp = wr.get(prov, {})
        for key, wsdim in DIMKEYS:
            # score: worklist target if rewritten else contributor original
            fx = ((wl.get(prov, {}) or {}).get('fixes', {}) or {}).get(key, {})
            orig_score = None
            try: orig_score = int(str(wrp.get(wsdim, {}).get('score')).strip())
            except: orig_score = wrp.get(wsdim, {}).get('score')
            score = fx.get('target_score', orig_score) if fx.get('needs_rewrite') else orig_score
            # justification: backfilled (revoiced) if rewritten else original
            just = wrp.get(wsdim, {}).get('justification', '')
            if fx.get('needs_rewrite'):
                bj = ((bfd.get(prov, {}) or {}).get(key, {}) or {})
                if bj.get('justification'): just = bj['justification']
            row[f'p{i}_{key}_rating'] = score
            row[f'p{i}_{key}_justification'] = just
    bf_rows.append(row)
with open(os.path.join(RUN, 'deliverables', 'backfill_forms.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=BF_COLS); w.writeheader()
    for r in bf_rows: w.writerow(r)

# ---------- eval_findings.csv: filter to L1 ----------
all_ef = list(csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv'))))
efcols = list(all_ef[0].keys())
with open(os.path.join(RUN, 'deliverables', 'eval_findings.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=efcols); w.writeheader()
    for r in all_ef:
        if r['level'] == 'L1': w.writerow(r)

print('external_feedback.csv:', len(ext_rows), 'rows (L1 needs-review)')
print('backfill_forms.csv:', len(bf_rows), 'rows (L1 backfill)')
print('eval_findings.csv: filtered to L1 (', sum(1 for r in all_ef if r['level']=='L1'), 'rows)')
