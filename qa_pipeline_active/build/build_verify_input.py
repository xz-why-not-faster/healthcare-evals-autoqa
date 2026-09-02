#!/usr/bin/env python3
"""Prep inputs for the post-categorize VERIFY passes. Reads deliverables/eval_findings.csv to find
the no_valid_stump and wrong_pdf tasks, then writes:

  <run>/verify/nostump_ids.json      task ids flagged no_valid_stump  (-> re-run stump + CB recheck)
  <run>/verify/wrongpdf_ids.json     task ids flagged wrong_pdf        (-> LLM PDF recheck)
  <run>/verify/pdf/<tid>.json        per wrong_pdf task: the flagged provider(s)' live user turns +
                                     extracted PDF text  (read by qa_active_pdfrecheck.js)
  <run>/verify/cb/<tid>.json         per no_stump task: the contributor's stump claim + their
                                     'response to eval'  (read by qa_active_stumprecheck.js)

Usage: python3 build_verify_input.py <V19.csv>   (run FROM the run folder; CSV also via $QA_INPUT_CSV)
"""
import csv, json, os, sys, re, io, urllib.request, logging
try:
    import pypdf; logging.getLogger("pypdf").setLevel(logging.ERROR)
except ImportError:
    pypdf = None

RUN = os.path.dirname(os.path.abspath(__file__))
WS = os.path.join(RUN, '..', 'workspace')
CSV = (sys.argv[1] if len(sys.argv) > 1 else None) or os.environ.get("QA_INPUT_CSV")
if not CSV:
    sys.exit("build_verify_input: pass the V19 input CSV as arg1 or set QA_INPUT_CSV")

os.makedirs(os.path.join(RUN, 'verify', 'pdf'), exist_ok=True)
os.makedirs(os.path.join(RUN, 'verify', 'cb'), exist_ok=True)

findings = list(csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv'))))
def has(r, d): return d in {x.strip() for x in (r.get('drivers', '') or '').split(',')}
nostump = [r['task_id'] for r in findings if has(r, 'no_valid_stump')]
wrongpdf = [r['task_id'] for r in findings if has(r, 'wrong_pdf')]

def case(t):
    fp = os.path.join(WS, f'task_{t}.json')
    return json.load(open(fp)) if os.path.exists(fp) else {}

# ---- PDF recheck inputs ----
pdfck = json.load(open(os.path.join(RUN, 'phase_pdfcheck.json'))) if os.path.exists(os.path.join(RUN, 'phase_pdfcheck.json')) else {}
def norm(s): return re.sub(r'\s+', ' ', (s or '')).strip()
def pdf_text(url):
    if not pypdf: return "[pypdf not installed]"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req, timeout=45).read()
        r = pypdf.PdfReader(io.BytesIO(data))
        raw = norm(' '.join(p.extract_text() or '' for p in r.pages))
        # strip repetitive screenshot.html / timestamp header noise to reveal real body text
        s = re.sub(r'\d{2}/\d{2}/\d{4},?\s*\d{2}:\d{2}\s*', '', raw)
        s = re.sub(r'chrome-extension://[a-z]+/screenshot\.html', '', s)
        s = re.sub(r'\s+\d+/\d+\s+', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()
    except Exception as e:
        return f"[extract failed: {e}]"

for t in wrongpdf:
    d = case(t); rec = {'task_id': t, 'providers': {}}
    for prov in ('chatgpt', 'claude', 'gemini'):
        pc = (pdfck.get(t, {}) or {}).get(prov, {})
        if not (isinstance(pc, dict) and pc.get('verdict') == 'WRONG_CONVO'):
            continue
        pv = d.get('providers', {}).get(prov, {}) or {}
        turns = [x.get('user', '') for x in (pv.get('transcript', {}) or {}).get('turns', []) if x.get('user')]
        sp = (pv.get('links', {}) or {}).get('session_pdf') or []
        url = sp[0].get('url') if sp else None
        body = pdf_text(url)[:1500] if url else "[no pdf url]"
        rec['providers'][prov] = {'live_user_turns': turns[:3], 'pdf': body, 'pdf_only_headers': len(body) < 60}
    json.dump(rec, open(os.path.join(RUN, 'verify', 'pdf', f'{t}.json'), 'w'), indent=1, ensure_ascii=False)

# ---- CB-feedback inputs (for no_stump tasks) ----
rows = list(csv.DictReader(open(CSV)))
by = {}
for r in rows:
    by.setdefault(r.get('task id'), []).append(r)
for t in nostump:
    rs = by.get(t, [])
    claims = {}
    resp = ''
    for r in rs:
        resp = resp or (r.get('response to eval') or '').strip()
        prov = (r.get('provider') or '').strip().lower()
        failed = (r.get('CB: model failed') or '').strip().lower().startswith('yes')
        cbf = (r.get('CB: model failure justification') or '').strip()
        if prov and failed and cbf:
            claims[prov] = {'cb_overall': r.get('overall rating'), 'claim': cbf}
    json.dump({'task_id': t, 'cb_claims': claims, 'response_to_eval': resp},
              open(os.path.join(RUN, 'verify', 'cb', f'{t}.json'), 'w'), indent=1, ensure_ascii=False)

json.dump(nostump, open(os.path.join(RUN, 'verify', 'nostump_ids.json'), 'w'))
json.dump(wrongpdf, open(os.path.join(RUN, 'verify', 'wrongpdf_ids.json'), 'w'))
print(f"verify inputs: {len(nostump)} no_valid_stump task(s), {len(wrongpdf)} wrong_pdf task(s)")
print(f"  -> re-run stump:      qa_active_justif.js        over verify/nostump_ids.json")
print(f"  -> PDF LLM recheck:    qa_active_pdfrecheck.js    over verify/wrongpdf_ids.json")
print(f"  -> CB-feedback recheck: qa_active_stumprecheck.js over the still-no-stump ids")
