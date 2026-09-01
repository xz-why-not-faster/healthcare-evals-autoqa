#!/usr/bin/env python3
"""Emit persona_updates.csv — a WIDE sheet, one row per persona-corrected backfill task.
Columns: task, original_persona, persona (slug), persona_name, persona_description.
Pulls this run's corrections plus any carryover runs passed on the command line."""
import csv, json, os, sys

RUN = os.path.dirname(os.path.abspath(__file__))

def persona_cols(name):
    n = (name or '').lower()
    if 'acute' in n:     return ('acute_care', 'Acute Care', 'Immediate, high-intent clarity during active health events.')
    if 'frontier' in n:  return ('frontier_health', 'Frontier Health', 'Deep, ongoing tracking for prosumers optimizing their health or tracking long-term outcomes.')
    if 'lifestyle' in n: return ('lifestyle', 'Lifestyle', 'Coaching and planning for ongoing lifestyle goals.')
    return ('', name or '', '')

def dim_rewrite_tasks(run_dir):
    """Tasks in this run that have >=1 dimension rewrite (i.e. also need a bot attempt)."""
    try:
        wl = json.load(open(f'{run_dir}/worklist.json'))
    except FileNotFoundError:
        return set()
    return {t for t, w in wl.items()
            if any(any(fx.get('needs_rewrite') for fx in pd['fixes'].values())
                   for pd in w['providers'].values())}

def rows_for_run(run_dir):
    pe = json.load(open(f'{run_dir}/phase_persona.json'))
    findings = {r['task_id']: r for r in csv.DictReader(open(f'{run_dir}/deliverables/eval_findings.csv'))}
    dims = dim_rewrite_tasks(run_dir)
    out = []
    for t, r in pe.items():
        if findings.get(t, {}).get('category') != 'backfill':
            continue
        if r.get('fits_assigned_persona', True):
            continue  # only emit real corrections
        slug, name, desc = persona_cols(r.get('suggested_persona'))
        out.append({
            'task_id': t,
            'original_persona': r.get('original_persona', ''),
            'persona': slug,
            'persona_name': name,
            'persona_description': desc,
            'needs_bot_attempt': 'yes' if t in dims else 'no',  # has dimension rewrites -> needs bot attempt
        })
    return out

# this run + any carryover run dirs passed as args
dirs = [RUN] + sys.argv[1:]
rows = []
seen = set()
for d in dirs:
    for row in rows_for_run(d):
        if row['task_id'] in seen:
            continue
        seen.add(row['task_id'])
        rows.append(row)

COLS = ['task_id', 'original_persona', 'persona', 'persona_name', 'persona_description', 'needs_bot_attempt']
with open(f'{RUN}/deliverables/persona_updates.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=COLS)
    w.writeheader()
    for r in rows:
        w.writerow(r)
print(f'persona_updates.csv: {len(rows)} tasks | needs_bot_attempt=yes: {sum(1 for r in rows if r["needs_bot_attempt"]=="yes")}')
for r in rows:
    print(f"  {r['task_id']} | {r['original_persona']} -> {r['persona']} | bot_attempt={r['needs_bot_attempt']}")
