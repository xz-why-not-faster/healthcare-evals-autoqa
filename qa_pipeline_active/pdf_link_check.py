#!/usr/bin/env python3
"""PDF-vs-link conversation match check. For each provider in each task's workspace case file:
download the uploaded session_pdf, extract its text, and check whether it is the SAME conversation
as the live share link (whose transcript is in the case file). Truncation/cut-off is OK; an
ENTIRELY DIFFERENT conversation is an artifact error.

Verdict per provider: MATCH (pdf covers the live convo), TRUNCATED_OK (matches but shorter),
WRONG_CONVO (pdf opening/content does not match the live transcript at all), NO_PDF, PDF_FAIL.

Writes phase_pdfcheck.json keyed by task_id: {chatgpt/claude/gemini: {verdict, detail}, task_artifact_pdf_issue: bool}.
Usage: python3 pdf_link_check.py <run_dir>   (reads <run>/pending_ids.json + workspace/)
"""
import json, os, sys, re, urllib.request, io
try:
    import pypdf
except ImportError:
    pypdf = None

RUN = sys.argv[1]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = os.path.join(ROOT, 'qa_pipeline_active', 'workspace')
ids = json.load(open(os.path.join(RUN, 'pending_ids.json')))

def norm(s):
    return re.sub(r'\s+', ' ', (s or '').lower()).strip()

def nospace(s):
    # keep ONLY a-z0-9 — robust to PDF letter-spacing ("b ik e r id in g"), curly-vs-straight
    # quotes/apostrophes ("I'm" vs "I'm"), and any punctuation differences between PDF and transcript.
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())

def pdf_text(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req, timeout=45).read()
        r = pypdf.PdfReader(io.BytesIO(data))
        return norm(' '.join(p.extract_text() or '' for p in r.pages))
    except Exception as e:
        return None

def user_turns(pv):
    return [t.get('user', '') for t in (pv.get('transcript', {}) or {}).get('turns', []) if t.get('user')]

def check_provider(pv):
    turns = user_turns(pv)
    url = None
    sp = (pv.get('links', {}) or {}).get('session_pdf') or []
    if sp and isinstance(sp, list):
        url = sp[0].get('url')
    if not url:
        return {'verdict': 'NO_PDF', 'detail': 'no session_pdf uploaded'}
    if not turns:
        return {'verdict': 'NO_TRANSCRIPT', 'detail': 'live transcript empty; cannot compare'}
    raw = pdf_text(url)
    if raw is None:
        return {'verdict': 'PDF_FAIL', 'detail': 'could not download/parse the PDF'}
    pns = nospace(raw)
    # ---- BODY probe: do the live user-turn openings appear in the PDF text? ----
    probes = []
    for i in (0, min(2, len(turns) - 1), min(4, len(turns) - 1), min(7, len(turns) - 1)):
        p = nospace(turns[i])[:40]
        if len(p) >= 15:
            probes.append(p)
    probes = list(dict.fromkeys(probes))
    hits = sum(1 for p in probes if p in pns)
    if hits:
        d = 'all probes matched' if hits == len(probes) else f'{hits}/{len(probes)} probes matched (may be truncated — OK)'
        return {'verdict': 'MATCH', 'detail': d}
    # ---- no body match: many of these are IMAGE-rendered PDFs whose only text is the repeated
    # page header (timestamp + conversation TITLE + share URL). Fall back to a title-vs-topic check. ----
    titles = re.findall(r'(?:am|pm|\d)\s+([a-z][a-z0-9 &\'\-]{4,60}?)\s+(?:chrome-extension|https?)://', norm(raw))
    title = max(set(titles), key=titles.count) if titles else ''
    convo = nospace(' '.join(turns))                    # all user turns, alnum
    if title:
        tw = [w for w in re.findall(r'[a-z0-9]+', title) if len(w) >= 4]
        overlap = sum(1 for w in tw if w in convo)
        if tw and overlap >= max(1, (len(tw) + 1) // 2):
            return {'verdict': 'UNREADABLE_PDF',
                    'detail': f'image-rendered PDF (body not extractable); header title "{title.strip()}" matches the conversation topic ({overlap}/{len(tw)} title words present) — same convo, not text-verifiable'}
        return {'verdict': 'WRONG_CONVO',
                'detail': f'image-rendered PDF whose header title "{title.strip()}" does NOT match the conversation ({overlap}/{len(tw)} title words present). live opening: "{norm(turns[0])[:70]}"'}
    if len(pns) < 400:
        return {'verdict': 'UNREADABLE_PDF',
                'detail': f'PDF extracted only {len(pns)} chars, no readable title — cannot verify (likely image-based)'}
    return {'verdict': 'WRONG_CONVO',
            'detail': f'none of {len(probes)} live user-turn openings appear in the PDF text. live opening: "{norm(turns[0])[:70]}"'}

out = {}
for _i, t in enumerate(ids, 1):
    print(f'[{_i}/{len(ids)}] {t}', flush=True)
    fp = os.path.join(WS, f'task_{t}.json')
    if not os.path.exists(fp):
        out[t] = {'error': 'no workspace file'}
        continue
    d = json.load(open(fp))
    rec = {}
    issue = False
    for prov in ['chatgpt', 'claude', 'gemini']:
        pv = d.get('providers', {}).get(prov, {}) or {}
        r = check_provider(pv)
        rec[prov] = r
        if r['verdict'] == 'WRONG_CONVO':
            issue = True
    rec['task_artifact_pdf_issue'] = issue
    out[t] = rec

json.dump(out, open(os.path.join(RUN, 'phase_pdfcheck.json'), 'w'), indent=1, ensure_ascii=False)
wrong = [t for t, r in out.items() if isinstance(r, dict) and r.get('task_artifact_pdf_issue')]
print(f'pdf_link_check: {len(ids)} tasks | WRONG_CONVO (artifact error -> needs review): {len(wrong)}')
for t in wrong:
    provs = [f"{p}:{out[t][p]['verdict']}" for p in ('chatgpt', 'claude', 'gemini') if out[t][p]['verdict'] == 'WRONG_CONVO']
    print(f'  {t}: {", ".join(provs)}')
