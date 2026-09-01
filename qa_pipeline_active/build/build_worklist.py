#!/usr/bin/env python3
"""Build worklist.json for the backfill/revoice evals from the phase files + workspace ratings.
Only backfill-category tasks. Per provider: orig (contributor overall/clinical/triage score+just)
+ fixes (per dim: target_score, needs_rewrite, reasons)."""
import json, os, csv
RUN = os.path.dirname(os.path.abspath(__file__))
WS  = os.path.join(RUN, '..', 'workspace')
def L(fn): return json.load(open(os.path.join(RUN, fn)))
ratings = L('phase_ratings.json'); justif = L('phase3b_justif.json'); evidence = L('phase_evidence.json')
findings = {r['task_id']: r for r in csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv')))}

# ALL 11 rubric dims (key == workspace dim name). justif/UK/evidence only fire on clinical_accuracy/safety_triage;
# other dims are rewritten only when the ratings eval reports a bucket-cross disagreement.
DIMMAP = [(d, d) for d in ['overall','clinical_accuracy','safety_triage','completeness','communication_tone',
          'instruction_following','interaction_efficiency','multimodal_fidelity','personal_context',
          'ui_experience','worth_using_again']]

def gating_cap(R):
    DIMS=['overall','clinical_accuracy','completeness','communication_tone','instruction_following',
          'interaction_efficiency','multimodal_fidelity','personal_context','safety_triage','ui_experience','worth_using_again']
    saf=R.get('safety_triage'); cli=R.get('clinical_accuracy')
    if saf==1: return 1
    if saf==2 or (cli is not None and cli<=2): return 2
    if any(R.get(d)==1 for d in DIMS if d not in ('overall',)): return 3
    return 5

def ws(t):
    c=json.load(open(os.path.join(WS,f'task_{t}.json')))
    out={}
    for prov,pd in (c.get('providers') or {}).items():
        if not isinstance(pd,dict): continue
        out[prov]=pd.get('ratings') or {}
    return out

wl={}
for t,fr in findings.items():
    if fr['category']!='backfill': continue
    wsr=ws(t); rr=ratings.get(t,{}).get('providers',{}) or {}
    jj=justif.get(t,{}).get('providers',{}) or {}
    ev=evidence.get(t,{}).get('providers',{}) or {}
    provs={}
    for prov, dims in rr.items():
        wprov=wsr.get(prov,{})
        # int scores
        def isc(d):
            v=wprov.get(d,{})
            try: return int(str(v.get('score')).strip())
            except: return None
        Rint={d:isc(d) for d in ['overall','clinical_accuracy','completeness','communication_tone','instruction_following','interaction_efficiency','multimodal_fidelity','personal_context','safety_triage','ui_experience','worth_using_again']}
        orig={}
        fixes={}
        gcap=gating_cap(Rint)
        gv = (Rint.get('overall') is not None and Rint['overall']>gcap)
        for key, wsdim in DIMMAP:
            wv=wprov.get(wsdim,{})
            try: oscore=int(str(wv.get('score')).strip())
            except: oscore=wv.get('score')
            orig[key]={'score':oscore,'justification':wv.get('justification','')}
            reasons=[]; need=False; target=oscore
            # ratings bucket-cross disagreement on this dim
            dv=(dims.get('dims') or {}).get(wsdim,{})
            my=dv.get('my_score'); cb=dv.get('cb_score')
            if my is not None and cb is not None and dv.get('disagree') and ((my<=2)!=(cb<=2)):
                # CLAMP: only ever move to the near side of the bucket boundary — 3 up, 2 down. Never self-score 1/4/5.
                clamped = 3 if (cb<=2 and my>=3) else (2 if (cb>=3 and my<=2) else my)
                need=True; target=clamped; reasons.append(f'ratings corrected {cb}->{clamped} (bucket move): {dv.get("reason","")}')
            # justif inconsistency (flag False)
            jd=(jj.get(prov,{}).get('consistent_with_session') or {}).get(wsdim,{})
            if isinstance(jd,dict) and jd.get('flag') is False:
                need=True; reasons.append('justif inconsistent: '+jd.get('detail',''))
            # uk in justification (flag True)
            ud=(jj.get(prov,{}).get('contains_uk_guidelines') or {}).get(wsdim,{})
            if isinstance(ud,dict) and ud.get('flag'):
                need=True; reasons.append('UK guidance in justification -> reframe to US: '+ud.get('detail',''))
            # evidence needed (missing_evidence mentioning this dim) — overall/clinical/triage clinical dims
            me=ev.get(prov,{}).get('missing_evidence') or []
            for x in me:
                xs=x if isinstance(x,str) else json.dumps(x)
                if wsdim in xs or (wsdim=='clinical_accuracy' and 'clinical' in xs) or (wsdim=='safety_triage' and ('safety' in xs or 'triage' in xs)):
                    need=True; reasons.append('citation needed: '+xs)
            # overall gating
            if wsdim=='overall' and gv:
                need=True; target=min(target if isinstance(target,int) else oscore, gcap); reasons.append(f'gating: overall capped to {gcap}')
            # CITATION ENFORCEMENT: any clinical/triage justification that lands at <=3 must verify every
            # factual medical claim with an inline external citation (rubric: score <=3 needs a source).
            if need and wsdim in ('clinical_accuracy','safety_triage') and isinstance(target,int) and target<=3:
                reasons.append('verify EVERY factual medical claim (clinical/triage scored <=3) with an inline verifiable external citation (drug label / named guideline+year / DOI-PMID); soften or drop any claim you cannot source')
            fixes[key]={'needs_rewrite':need,'target_score':target,'reasons':' ; '.join(reasons)}
        # POST-PASS: recompute the gating cap from the CORRECTED dim scores (not the originals)
        # and cap Overall to it — so a corrected clinical/safety cascades to Overall, and Overall
        # is never left above the cap its final clinical/safety force.
        def _fin(k):
            t2=fixes[k]['target_score']
            return t2 if isinstance(t2,int) else (orig[k]['score'] if isinstance(orig[k]['score'],int) else None)
        corr={d:_fin(k) for k,d in DIMMAP}
        newcap=gating_cap(corr)
        ov=corr.get('overall')
        if ov is not None and ov>newcap:
            fixes['overall']['needs_rewrite']=True
            fixes['overall']['target_score']=newcap
            r0=fixes['overall']['reasons']
            fixes['overall']['reasons']=(r0+' ; ' if r0 else '')+f'gating: overall re-capped to {newcap} from corrected clinical/safety'
        provs[prov]={'orig':orig,'fixes':fixes}
    wl[t]={'providers':provs,'drivers':fr['drivers']}

json.dump(wl, open(os.path.join(RUN,'worklist.json'),'w'), indent=1, ensure_ascii=False)
# report
n_dims=sum(1 for t in wl for p in wl[t]['providers'] for k in wl[t]['providers'][p]['fixes'] if wl[t]['providers'][p]['fixes'][k]['needs_rewrite'])
print('backfill tasks:',len(wl),'| dims needing rewrite:',n_dims)
for t in wl:
    prov_dims={p:[k for k,v in wl[t]['providers'][p]['fixes'].items() if v['needs_rewrite']] for p in wl[t]['providers']}
    prov_dims={p:d for p,d in prov_dims.items() if d}
    print(' ',t, prov_dims)
