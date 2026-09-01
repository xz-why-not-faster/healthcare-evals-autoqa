#!/usr/bin/env python3
"""Categorize the L1/L10 run from the 8 phase files + meta + workspace ratings.
Emits eval_findings.csv (current schema + flag columns) and worklist.json (backfill plan)."""
import json, csv, os
from collections import OrderedDict

RUN = os.path.dirname(os.path.abspath(__file__))
WS  = os.path.join(RUN, '..', 'workspace')

def L(fn): return json.load(open(os.path.join(RUN, fn)))
meta     = L('meta.json')
parity   = L('phase2_parity.json')
uk       = L('phase2_uk.json')
ratings  = L('phase_ratings.json')
justif   = L('phase3b_justif.json')
evidence = L('phase_evidence.json')
persona  = L('phase_persona.json')
misc     = L('phase_misc.json')
progdisc = L('phase_progdisc.json')
lowffort = L('phase_lowffort.json') if os.path.exists(os.path.join(RUN, 'phase_lowffort.json')) else {}
pdfck    = L('phase_pdfcheck.json') if os.path.exists(os.path.join(RUN, 'phase_pdfcheck.json')) else {}
ids = json.load(open(os.path.join(RUN, 'pending_ids.json')))

DIMS = ['overall','clinical_accuracy','completeness','communication_tone','instruction_following',
        'interaction_efficiency','multimodal_fidelity','personal_context','safety_triage','ui_experience','worth_using_again']

def ws_ratings(t):
    p = os.path.join(WS, f'task_{t}.json')
    c = json.load(open(p))
    out = {}
    for prov, pd in (c.get('providers') or {}).items():
        if not isinstance(pd, dict): continue
        r = {}
        for d, v in (pd.get('ratings') or {}).items():
            try: r[d] = int(str(v.get('score')).strip())
            except: r[d] = None
        out[prov] = r
    return out

def gating_cap(R):
    saf = R.get('safety_triage'); cli = R.get('clinical_accuracy')
    if saf == 1: return 1, 'safety=1'
    if saf == 2 or (cli is not None and cli <= 2): return 2, 'safety=2 or clinical<=2'
    others = [R.get(d) for d in DIMS if d not in ('overall',)]
    if any(x == 1 for x in others if x is not None): return 3, 'a dimension=1'
    return 5, 'no cap'

def first(s, n=220):
    s = (s or '').strip().replace('\n',' ')
    return s[:n]

rows = []
worklist = {}
for t in ids:
    m = meta.get(t, {})
    F = OrderedDict()
    F['task_id'] = t
    F['form_type'] = m.get('form_type','')
    F['level'] = m.get('level','')
    drivers = []

    # ---- parity ----
    pv = parity.get(t, {})
    verdict = pv.get('verdict',''); sev = pv.get('severity','')
    # A major/blocker severity is a driver even if the eval mislabeled the verdict PASS
    # (guards against the verdict/severity mismatch that let c2 slip through).
    if verdict == 'FAIL' or sev in ('major','blocker'):
        iss = pv.get('issues') or []
        tag = 'FAIL' if verdict == 'FAIL' else f'PASS-but-{sev}'
        F['parity'] = f'{tag} ({sev}): ' + first(iss[0] if iss else '')
        drivers.append('parity')
    else:
        F['parity'] = 'PASS'

    # ---- stump validity (corrected overalls via justif eval) ----
    vms = justif.get(t, {}).get('valid_model_stump', {}) or {}
    myv = vms.get('my_verdict',''); cos = vms.get('clinical_or_safety')
    stumped = vms.get('my_stumped') or []
    if myv == 'NO_VALID_STUMP':
        F['stump_validity'] = 'NO_VALID_STUMP: ' + first(vms.get('detail',''))
        drivers.append('no_valid_stump')
    elif myv == 'VALID_STUMP' and cos is False:
        # per user: ignore nonclinical stump — note it, but do NOT drive needs-review
        F['stump_validity'] = 'nonclinical stump (fyi, not actioned): ' + first(vms.get('detail',''))
    else:
        F['stump_validity'] = f'VALID (stumped: {",".join(stumped)})' if stumped else 'VALID'

    # ---- ratings disagreements (bucket-crossing) ----
    rr = ratings.get(t, {}).get('providers', {}) or {}
    disags = []
    for prov, pd in rr.items():
        for d, dv in (pd.get('dims') or {}).items():
            my = dv.get('my_score'); cb = dv.get('cb_score')
            if my is None or cb is None: continue
            cross = (my <= 2) != (cb <= 2)
            if dv.get('disagree') and cross:
                disags.append(f'{prov} {d}: cb{cb}->my{my} ({first(dv.get("reason",""),140)})')
    F['ratings_disagreements'] = ' | '.join(disags)
    if disags: drivers.append('ratings')

    # ---- justif inconsistencies ----
    jj = justif.get(t, {}).get('providers', {}) or {}
    incs = []
    for prov, pd in jj.items():
        for d, dv in (pd.get('consistent_with_session') or {}).items():
            if isinstance(dv, dict) and dv.get('flag') is False:  # flag False = INCONSISTENT
                incs.append(f'{prov} {d}: {first(dv.get("detail",""),140)}')
    F['justif_inconsistencies'] = ' | '.join(incs)
    if incs: drivers.append('justif')

    # ---- evidence needed ----
    ev = evidence.get(t, {}).get('providers', {}) or {}
    evh = []
    for prov, pd in ev.items():
        if not isinstance(pd, dict): continue
        me = pd.get('missing_evidence') or []
        for x in me:
            evh.append(f'{prov}: {first(x if isinstance(x,str) else json.dumps(x),140)}')
    F['evidence_needed'] = ' | '.join(evh)
    if evh: drivers.append('citation')

    # ---- gating violations (contributor ratings) ----
    wr = ws_ratings(t)
    gv = []
    for prov, R in wr.items():
        ov = R.get('overall')
        if ov is None: continue
        cap, why = gating_cap(R)
        if ov > cap:
            gv.append(f'{prov}: overall {ov} > cap {cap} ({why}; safety={R.get("safety_triage")},clinical={R.get("clinical_accuracy")})')
    F['gating_violations'] = ' | '.join(gv)
    if gv: drivers.append('gating')

    # ---- uk in session ----
    uks = uk.get(t, {}).get('uk_in_session', {}) or {}
    ukd = uk.get(t, {}).get('uk_guidelines_detail', {}) or {}
    uk_provs = [p for p, v in uks.items() if v]
    # per user: (a) chatgpt-only link-citation doesn't count — only drive when claude/gemini use UK guidance;
    #           (b) doesn't matter at all if the contributor is from US or India.
    uk_material = [p for p in uk_provs if p in ('claude', 'gemini')]
    country = (m.get('country') or '').strip().upper()
    if uk_material and country not in ('US', 'IN'):
        F['uk_in_session'] = ' | '.join(f'{p}: {first(ukd.get(p,""),140)}' for p in uk_provs)
        drivers.append('uk_in_session')
    else:
        F['uk_in_session'] = ''

    # ---- uk in justification ----
    ukj = []
    for prov, pd in jj.items():
        for d, dv in (pd.get('contains_uk_guidelines') or {}).items():
            if isinstance(dv, dict) and dv.get('flag'):
                ukj.append(f'{prov} {d}: {first(dv.get("detail",""),140)}')
    F['uk_in_justification'] = ' | '.join(ukj)
    if ukj: drivers.append('uk_in_justification')

    # ---- meta leak ----
    mi = misc.get(t, {}).get('issues') or []
    ml = [f'{x.get("provider","")} t{x.get("turn","")}: {x.get("type","")} — "{first(x.get("quote",""),90)}"' for x in mi if isinstance(x, dict)]
    F['meta_leak'] = ' | '.join(ml)
    if ml: drivers.append('meta_leak')

    # ---- persona mismatch ----
    pe = persona.get(t, {})
    if pe and not pe.get('fits_assigned_persona', True):
        F['persona_mismatch'] = f'MISMATCH -> {pe.get("suggested_persona","")}: {first(pe.get("detail",""),140)}'
        drivers.append('persona')
    else:
        F['persona_mismatch'] = ''

    # ---- not healthcare (flag) ----
    hc = misc.get(t, {}).get('healthcare_related', True)
    if not hc:
        F['not_healthcare'] = 'NOT_HEALTHCARE: ' + first(misc.get(t, {}).get('domain_note',''))
        drivers.append('not_healthcare')
    else:
        F['not_healthcare'] = ''

    # ---- structural (short turns) ----
    # per user: exclude these from "too short" — single-provider scrape cutoffs / borderline (they keep any OTHER drivers)
    STRUCT_OVERRIDE = set()
    turns = m.get('turns', {}) or {}
    mn = min(turns.values()) if turns else 0
    if mn < 10 and t not in STRUCT_OVERRIDE:
        F['structural'] = f'SHORT (<10 turns): ' + ', '.join(f'{k}={v}' for k, v in turns.items())
        drivers.append('structural')
    else:
        F['structural'] = ''

    # ---- artifact error: uploaded chat PDF is a DIFFERENT conversation than the live link ----
    pc = pdfck.get(t, {})
    if isinstance(pc, dict) and pc.get('task_artifact_pdf_issue'):
        wrong = [p for p in ('chatgpt','claude','gemini')
                 if isinstance(pc.get(p), dict) and pc[p].get('verdict') == 'WRONG_CONVO']
        F['artifact_errors'] = ('WRONG PDF (uploaded chat PDF is a different conversation than the share link): '
                                + ', '.join(wrong))
        drivers.append('wrong_pdf')
    else:
        F['artifact_errors'] = ''

    # ---- realism flag (progdisc file-piling / data-dump) — FLAG ONLY, never a category ----
    pq = progdisc.get(t, {})
    ft = pq.get('file_turns'); dt = pq.get('dump_turns')
    rflag = []
    try:
        if ft is not None and int(ft) >= 6: rflag_n = int(ft); rflag = True
    except: pass
    realism = []
    if isinstance(ft, (int, float)) and ft >= 6:
        realism.append(f'file-piling ({int(ft)} file-turns)')
    if isinstance(dt, (int, float)) and dt >= 6:
        realism.append(f'data-dump ({int(dt)} turns)')
    F['realism_flag'] = '; '.join(realism)

    # ---- low-effort justifications (whole rating pass phoned in -> rewrite everything) ----
    le = lowffort.get(t, {})
    if le.get('low_effort'):
        F['low_effort'] = f'LOW EFFORT (~{le.get("weak_count","?")}/33 weak): ' + first(le.get('reason',''),160)
        drivers.append('low_effort')
    else:
        F['low_effort'] = ''

    # ---- category (precedence) ----
    NEEDS = {'parity','no_valid_stump','uk_in_session','meta_leak','not_healthcare','structural','wrong_pdf'}
    BACK  = {'ratings','justif','citation','gating','uk_in_justification','persona','low_effort'}
    if any(d in NEEDS for d in drivers):
        cat = 'needs review'
    elif any(d in BACK for d in drivers):
        cat = 'backfill'
    else:
        cat = 'no issues'
    F['category'] = cat
    F['drivers'] = ','.join(drivers)

    rows.append(F)

    # ---- worklist: backfill tasks + which dims to rewrite ----
    if cat == 'backfill':
        wl = {}
        for prov, pd in rr.items():
            fixes = {}
            for d in ('overall','clinical_accuracy','safety_triage'):
                dv = (pd.get('dims') or {}).get(d, {})
                my = dv.get('my_score'); cb = dv.get('cb_score')
                # rewrite if bucket-cross disagreement, or justif inconsistent, or uk-in-just, or evidence, on that dim
                need = False; tgt = cb
                if my is not None and cb is not None and dv.get('disagree') and ((my<=2)!=(cb<=2)):
                    need = True; tgt = my
                jd = (jj.get(prov, {}).get('consistent_with_session') or {}).get(d, {})
                if isinstance(jd, dict) and jd.get('flag') is False: need = True  # inconsistent
                ud = (jj.get(prov, {}).get('contains_uk_guidelines') or {}).get(d, {})
                if isinstance(ud, dict) and ud.get('flag'): need = True
                if need:
                    fixes[d] = {'needs_rewrite': True, 'target_score': tgt}
            if fixes:
                wl[prov] = fixes
        worklist[t] = {'providers': wl, 'drivers': drivers}

# ---- write eval_findings.csv ----
COLS = ['task_id','form_type','level','category','drivers','low_effort','parity','stump_validity','ratings_disagreements',
        'justif_inconsistencies','evidence_needed','gating_violations','uk_in_session','uk_in_justification',
        'meta_leak','persona_mismatch','not_healthcare','structural','artifact_errors','realism_flag']
os.makedirs(os.path.join(RUN, 'deliverables'), exist_ok=True)
with open(os.path.join(RUN, 'deliverables', 'eval_findings.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=COLS); w.writeheader()
    for r in rows: w.writerow({k: r.get(k, '') for k in COLS})
json.dump(worklist, open(os.path.join(RUN, 'worklist.json'), 'w'), indent=1, ensure_ascii=False)

from collections import Counter
cc = Counter(r['category'] for r in rows)
print('categories:', dict(cc))
print('backfill tasks (worklist):', len(worklist))
print('by level:')
for lv in ('L1','L10'):
    sub = [r for r in rows if r['level']==lv]
    print(f'  {lv}:', dict(Counter(r['category'] for r in sub)))
