#!/usr/bin/env python3
"""Apply the VERIFY-pass results, then re-categorize. Run FROM the run folder.

  --pdf   <pdfrecheck.output>     clear task_artifact_pdf_issue for tasks the LLM did NOT confirm WRONG_CONVO
  --stump <justif rerun .output>  flip no_valid_stump -> valid where the re-run now finds a stump
  --cb    <stumprecheck .output>  flip no_valid_stump -> valid where the CB-feedback re-adjudication holds

All optional; each is a workflow .output ({result:[...]} or [...]). Updates phase_pdfcheck.json +
phase3b_justif.json in place, then re-runs categorize.py so eval_findings/worklist reflect the flips.

Usage: python3 apply_verify.py [--pdf F] [--stump F] [--cb F]
"""
import json, os, sys, subprocess, argparse

RUN = os.path.dirname(os.path.abspath(__file__))
def load_out(p):
    d = json.load(open(p)); return d['result'] if isinstance(d, dict) and 'result' in d else d

ap = argparse.ArgumentParser()
ap.add_argument('--pdf'); ap.add_argument('--stump'); ap.add_argument('--cb')
a = ap.parse_args()

# ---- 1) PDF recheck: keep wrong_pdf only where the LLM confirms a WRONG_CONVO provider ----
if a.pdf and os.path.exists(a.pdf):
    pc = json.load(open(os.path.join(RUN, 'phase_pdfcheck.json')))
    cleared = []
    for r in load_out(a.pdf):
        t = r.get('task_id'); provs = r.get('providers', {}) or {}
        confirmed = [p for p, v in provs.items() if isinstance(v, dict) and v.get('verdict') == 'WRONG_CONVO']
        if t in pc and isinstance(pc[t], dict):
            pc[t]['task_artifact_pdf_issue'] = bool(confirmed)
            pc[t]['_llm_recheck'] = ('confirmed WRONG_CONVO: ' + ', '.join(confirmed)) if confirmed \
                else 'downgraded — LLM found SAME_CONVO / UNVERIFIABLE, not a different conversation'
            if not confirmed: cleared.append(t)
    json.dump(pc, open(os.path.join(RUN, 'phase_pdfcheck.json'), 'w'), indent=1, ensure_ascii=False)
    print(f"[pdf] cleared {len(cleared)} false-positive wrong_pdf flag(s): {[t[-6:] for t in cleared]}")

# ---- 2/3) stump flips (re-run and/or CB recheck) ----
jf = os.path.join(RUN, 'phase3b_justif.json')
justif = json.load(open(jf))
flipped = []
def flip(t, provs, detail):
    if t not in justif: return
    vs = justif[t].setdefault('valid_model_stump', {})
    vs['my_verdict'] = 'VALID_STUMP'; vs['my_stumped'] = provs or vs.get('my_stumped', [])
    vs['clinical_or_safety'] = True; vs['agree'] = True
    vs['detail'] = detail
    flipped.append(t)

if a.stump and os.path.exists(a.stump):
    for r in load_out(a.stump):
        vs = (r.get('valid_model_stump') or {})
        if vs.get('my_verdict') == 'VALID_STUMP':
            flip(r['task_id'], vs.get('my_stumped', []), 'VERIFY re-run: stump held on a second pass. ' + (vs.get('detail') or ''))

if a.cb and os.path.exists(a.cb):
    for r in load_out(a.cb):
        if r.get('verdict') == 'STUMP_HOLDS' and r['task_id'] not in flipped:
            flip(r['task_id'], r.get('stumped_providers', []), 'VERIFY CB-feedback recheck upheld the stump. ' + (r.get('reasoning') or ''))

if flipped:
    json.dump(justif, open(jf, 'w'), indent=1, ensure_ascii=False)
print(f"[stump] flipped {len(flipped)} no_valid_stump -> VALID_STUMP: {[t[-6:] for t in flipped]}")

# ---- re-categorize so the flips + PDF clears cascade into findings/worklist ----
print("[verify] re-running categorize ...")
subprocess.run([sys.executable, os.path.join(RUN, 'categorize.py')], check=True)
