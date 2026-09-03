#!/usr/bin/env python3
"""Two conversation tables that get adjudicated by hand (for now):

  deliverables/redos_needs_review.csv  — every REDO (redo==yes) still 'needs review', any level.
      cols: task_id, attempter, level_of_redo, reason, initial_attempt_id, prior_eval
      (`prior_eval` = what the initial attempt's last eval said — from prior-eval-lookup on the
       initial attempt id; that's the "changes since last attempt" starting point.)

  deliverables/l10_needs_review.csv    — L10 'needs review' tasks that are NOT redos.
      cols: task_id, attempter, reason, changes_since_last_eval, reviewer_commentary
      (`changes_since_last_eval` = driver delta vs this task's previous eval, via prior-eval-lookup;
       `reviewer_commentary` = the L0 reviewer's notes from the combined CSV.)

Reads the run's deliverables/eval_findings.csv + the combined V19 CSV (redo / initial attempt id /
attempt level / L0 notes). usage: build_redos.py <combined.csv>  (or $QA_INPUT_CSV)
"""
import csv, json, os, subprocess, sys

RUN = os.path.dirname(os.path.abspath(__file__))
CSV = (sys.argv[1] if len(sys.argv) > 1 else None) or os.environ.get("QA_INPUT_CSV")
if not CSV:
    sys.exit("build_redos: pass the combined V19 CSV as arg1 or set QA_INPUT_CSV")
LOOKUP = os.path.expanduser("~/Documents/task-scraper/.claude/skills/prior-eval-lookup/find_prior_eval.py")
NEEDS = {'parity','no_valid_stump','uk_in_session','meta_leak','not_healthcare','structural','wrong_pdf'}

findings = list(csv.DictReader(open(os.path.join(RUN, 'deliverables', 'eval_findings.csv'))))
# one representative CSV row per task (task-level fields are duplicated across the 3 provider rows)
crow, l0notes = {}, {}
for r in csv.DictReader(open(CSV)):
    t = r.get('task id')
    crow.setdefault(t, r)
    # collect any non-empty L0 reviewer notes across the task's rows
    for k in ('L0 ratings errors notes','L0 session errors notes','L0 artifact errors notes',
              'L0 misc errors notes','L0 additional notes','L0 QC feedback'):
        v = (r.get(k) or '').strip()
        if v: l0notes.setdefault(t, []).append(f"{k.replace('L0 ','').replace(' notes','')}: {v}")

def g(t, k): return (crow.get(t, {}).get(k) or '').strip()
def reason(f): return ', '.join(d for d in (f.get('drivers','') or '').split(',') if d in NEEDS)
def lookup(flag, val):
    try:
        return subprocess.run([sys.executable, LOOKUP, flag, val], capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:
        return f"(lookup failed: {e})"

def first_line(s):
    # condense a prior-eval-lookup dump to its category/drivers line
    for ln in (s or '').splitlines():
        if ln.startswith('run:'): return ln.replace('run: ', '')
    return s.splitlines()[0] if s else '(no prior eval found)'

redos, l10 = [], []
for f in findings:
    if f['category'] != 'needs review':
        continue
    t = f['task_id']
    is_redo = g(t, 'redo').lower() == 'yes'
    if is_redo:
        init = g(t, 'initial attempt id')
        redos.append({
            'task_id': t, 'attempter': g(t, 'submitted by'),
            'level_of_redo': g(t, 'attempt level'), 'reason': reason(f),
            'initial_attempt_id': init,
            'prior_eval': first_line(lookup('--attempt', init)) if init else '(no initial attempt id)',
        })
    elif f['level'] == 'L10':
        l10.append({
            'task_id': t, 'attempter': g(t, 'submitted by'), 'reason': reason(f),
            'changes_since_last_eval': first_line(lookup('--task', t)),
            'reviewer_commentary': '  '.join(l0notes.get(t, [])) or '(none)',
        })

def write(name, cols, rows):
    with open(os.path.join(RUN, 'deliverables', name), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow(r)

write('redos_needs_review.csv', ['task_id','attempter','level_of_redo','reason','initial_attempt_id','prior_eval'], redos)
write('l10_needs_review.csv', ['task_id','attempter','reason','changes_since_last_eval','reviewer_commentary'], l10)
print(f"redos_needs_review.csv: {len(redos)} redo task(s) still needs-review")
print(f"l10_needs_review.csv: {len(l10)} non-redo L10 needs-review task(s)")
