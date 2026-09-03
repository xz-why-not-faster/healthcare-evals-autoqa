#!/usr/bin/env python3
"""Find the most recent prior eval of a given attempt id (or task id) in the run logs.

Used for redos (look up the eval/feedback the `initial attempt id` or `L0 reviewed attempt id`
got last time) without a structured history DB — it just scans the run folders on disk. Searches
both the live run folders and the local archive; sorts newest-first by run-folder date.

For each match it reports: run, task_id, attempt_id, attempter, level, our category + drivers, and
the reviewer-facing feedback (external / contributor) if that run wrote any.

usage:
  find_prior_eval.py --attempt <attempt_id>
  find_prior_eval.py --task <task_id>
  find_prior_eval.py --attempt <id> --all      # list every run it appears in, not just the newest
"""
import argparse, csv, glob, json, os

ROOTS = [
    os.path.expanduser("~/Documents/task-scraper/qa_pipeline_active"),
    os.path.expanduser("~/Documents/task-scraper-archive-2026-09-01/extracted/qa_pipeline_active"),
]

def run_dirs():
    ds = []
    for root in ROOTS:
        ds += glob.glob(os.path.join(root, "20[0-9][0-9]-[0-9][0-9]-*"))
    # newest first: folder names start with YYYY-MM-DD so lexical sort = chronological
    return sorted([d for d in ds if os.path.isdir(d)], key=lambda d: os.path.basename(d), reverse=True)

def load(fp):
    try: return json.load(open(fp))
    except Exception: return None

def rows(fp):
    try: return list(csv.DictReader(open(fp)))
    except Exception: return []

def find(attempt=None, task=None, show_all=False):
    hits = []
    for d in run_dirs():
        meta = load(os.path.join(d, "meta.json")) or {}
        # match tasks in this run by attempt_id or task_id
        matched = []
        for tid, m in meta.items():
            if not isinstance(m, dict): continue
            if (attempt and m.get("attempt_id") == attempt) or (task and tid == task):
                matched.append((tid, m))
        if not matched:
            continue
        ef = {r["task_id"]: r for r in rows(os.path.join(d, "deliverables", "eval_findings.csv"))}
        ext = {r["task_id"]: r for r in rows(os.path.join(d, "deliverables", "external_feedback.csv"))}
        cfb = {r["task_id"]: r for r in rows(os.path.join(d, "deliverables", "contributor_feedback.csv"))}
        for tid, m in matched:
            f = ef.get(tid, {})
            fb = ""
            if tid in ext:
                e = ext[tid]
                fb = " | ".join(f"{k.replace('_external','')}: {e[k]}" for k in e
                                if k.endswith("_external") and e[k] and e[k].strip().lower() != "n/a")
            elif tid in cfb:
                fb = cfb[tid].get("contributor feedback", "")
            hits.append({
                "run": os.path.basename(d), "task_id": tid,
                "attempt_id": m.get("attempt_id", ""), "attempter": m.get("attempter", ""),
                "level": m.get("level", ""),
                "category": f.get("category", "(no eval_findings row)"),
                "drivers": f.get("drivers", ""), "feedback": fb,
            })
        if not show_all:
            break  # newest run with a match is enough
    return hits

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempt"); ap.add_argument("--task"); ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if not (a.attempt or a.task):
        raise SystemExit("pass --attempt <id> and/or --task <id>")
    hits = find(a.attempt, a.task, a.all)
    if not hits:
        print(f"No prior eval found for {'attempt '+a.attempt if a.attempt else 'task '+a.task} "
              f"in {len(run_dirs())} run folder(s).")
    for h in hits:
        print("=" * 80)
        print(f"run: {h['run']}   level: {h['level']}   category: {h['category']}")
        print(f"task {h['task_id']}   attempt {h['attempt_id']}   attempter {h['attempter']}")
        if h["drivers"]:  print(f"drivers: {h['drivers']}")
        if h["feedback"]: print(f"feedback: {h['feedback'][:600]}")
