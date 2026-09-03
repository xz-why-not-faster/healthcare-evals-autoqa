#!/usr/bin/env python3
"""Diff a redo attempt against its initial attempt — a sense of what the contributor changed.

Compares the two attempts' CASE FILES (per-run `cases/task_<id>.json` snapshots) across: session
links, the 11 ratings scores, which justifications changed, produced artifacts, and transcript turn
counts — per provider. Used by build_redos.py for the "changes since last attempt" column.

The initial attempt's case file is located by scanning run folders (live + archive) for the run whose
meta.json maps this task to the initial attempt id, then reading that run's cases/ snapshot. (Snapshots
started 2026-09-01; older attempts predate them and will report "initial attempt not snapshotted".)

usage: build_attempt_diff.py <task_id> <initial_attempt_id> [<current_case.json>]
"""
import glob, json, os, sys

ROOTS = [os.path.expanduser("~/Documents/task-scraper/qa_pipeline_active"),
         os.path.expanduser("~/Documents/task-scraper-archive-2026-09-01/extracted/qa_pipeline_active")]
DIMS = ['overall','clinical_accuracy','completeness','communication_tone','instruction_following',
        'interaction_efficiency','multimodal_fidelity','personal_context','safety_triage',
        'ui_experience','worth_using_again']

def _runs():
    ds = []
    for r in ROOTS: ds += glob.glob(os.path.join(r, "20[0-9][0-9]-[0-9][0-9]-*"))
    return sorted([d for d in ds if os.path.isdir(d)], key=os.path.basename, reverse=True)

def _load(fp):
    try: return json.load(open(fp))
    except Exception: return None

def find_initial_case(task_id, initial_attempt_id):
    for d in _runs():
        meta = _load(os.path.join(d, "meta.json")) or {}
        m = meta.get(task_id)
        if isinstance(m, dict) and m.get("attempt_id") == initial_attempt_id:
            snap = os.path.join(d, "cases", f"task_{task_id}.json")
            if os.path.exists(snap):
                return snap, os.path.basename(d)
            return None, os.path.basename(d)  # run found but no snapshot (pre-snapshot era)
    return None, None

def _prov(case, p):
    return (case.get("providers", {}) or {}).get(p, {}) or {}

def diff_attempts(task_id, initial_attempt_id, cur_case_path):
    cur = _load(cur_case_path)
    if not cur:
        return "current case file not found"
    init_path, run = find_initial_case(task_id, initial_attempt_id)
    if not init_path:
        return f"initial attempt not snapshotted{f' (last seen in {run})' if run else ''} — no field diff"
    init = _load(init_path) or {}
    parts = []
    for p in ("chatgpt", "claude", "gemini"):
        c, i = _prov(cur, p), _prov(init, p)
        if not c and not i: continue
        seg = []
        # links
        cl = ((c.get("links", {}) or {}).get("session_link") or [{}])[0].get("url", "")
        il = ((i.get("links", {}) or {}).get("session_link") or [{}])[0].get("url", "")
        if cl != il: seg.append("link changed")
        # scores + justifications
        cr, ir = c.get("ratings", {}) or {}, i.get("ratings", {}) or {}
        sc = [f"{d.split('_')[0]} {ir.get(d,{}).get('score')}→{cr.get(d,{}).get('score')}"
              for d in DIMS if str(ir.get(d,{}).get('score')) != str(cr.get(d,{}).get('score'))]
        if sc: seg.append("scores: " + ", ".join(sc))
        jch = [d.split('_')[0] for d in DIMS
               if (ir.get(d,{}).get('justification') or '') != (cr.get(d,{}).get('justification') or '')]
        if jch: seg.append("justif changed: " + ", ".join(jch))
        # transcript turns + artifacts
        ct = (c.get("transcript", {}) or {}).get("num_turns")
        it = (i.get("transcript", {}) or {}).get("num_turns")
        if ct != it: seg.append(f"turns {it}→{ct}")
        if seg: parts.append(f"[{p}] " + "; ".join(seg))
    return " | ".join(parts) if parts else f"no field changes vs initial ({run})"

if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    task, init = sys.argv[1], sys.argv[2]
    cur = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "workspace", f"task_{task}.json")
    print(diff_attempts(task, init, cur))
