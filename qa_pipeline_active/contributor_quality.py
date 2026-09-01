#!/usr/bin/env python3
"""
contributor_quality.py — per-attempter QA quality rollup (runs after backfill).

Accumulates EVERY attempt ever evaluated (union of all run folders' eval_results.csv,
deduped by attempt_id, latest run wins) and rolls it up to one row per attempter.
Writes:
  eval_history/all_attempts.csv        attempt-level master (grows each run)
  eval_history/contributor_quality.csv the per-attempter summary (the deliverable)

quality_score is a 0-100 weighted outcome (no-issues=1.0, backfill=0.6, needs-review=0.2,
wiped=0.0) computed on an ADJUSTED category that IGNORES uk-in-conversation (p2_uk_in_session),
since a UK-in-session flag is the model's behavior, not the contributor's fault.

Usage: python contributor_quality.py   (no args; scans qa_pipeline_active/<run>/eval_results.csv)
"""
import csv, glob, os, collections, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QA = os.path.join(ROOT, "qa_pipeline_active")
HIST = os.path.join(ROOT, "eval_history")
CANON = os.path.join(QA, "V19_ AutoQA Setup - full data per task.csv")

# error flag -> (candidate columns new/old, predicate on the cell value)
def _sw(*pre): return lambda v: v.strip().lower().startswith(pre)
def _isset(*bad): return lambda v: bool(v.strip()) and not v.strip().lower().startswith(bad)
FLAGS = [
    ("broken_link",        ["p1_broken_link"],                              _sw("yes")),
    ("front_loaded",       ["p2_progressive_disclosure", "progressive_disclosure"], _sw("front-loaded")),
    ("parity_fail",        ["p2_parity_issue"],                             _isset("no", "n/a", "n·a")),
    ("uk_in_session",      ["p2_uk_in_session"],                            _sw("fail")),
    ("no_valid_stump",     ["p2_no_valid_stump"],                           _sw("yes")),
    ("safety_punt",        ["p2_safety_punt"],                              _sw("fail")),
    ("artifact_issue",     ["p3_artifacts_issues", "p3a_artifacts_issues"], _sw("yes")),
    ("dummy_upload",       ["p3_dummy_artifacts", "p3a_dummy_artifacts"],   _isset("no", "n/a", "n·a")),
    ("uk_in_ratings",      ["p4_uk_in_ratings", "p3b_uk_in_ratings"],       _isset("no", "n/a", "n·a")),
    ("justif_inconsistent",["p4_ratings_consistency", "p3b_ratings_consistency"], _sw("inconsistent")),
    ("missing_evidence",   ["p4_low_score_evidence", "low_score_evidence"], _sw("missing")),
    ("gating",             ["p4_gating_violation", "gating_violation"],     _isset("ok", "n/a", "n·a")),
    ("persona",            ["p5_corrected_persona", "corrected_persona"],   lambda v: bool(v.strip())),
]
# which flags count against the quality score (NOT uk_in_session — unfair), by severity tier
WIPED = {"broken_link"}
REVIEW = {"parity_fail", "no_valid_stump", "safety_punt", "artifact_issue"}  # uk_in_session excluded
BACKFILL = {"dummy_upload", "uk_in_ratings", "justif_inconsistent", "missing_evidence", "gating", "persona"}


def get(row, cands):
    for c in cands:
        if c in row and row[c] != "":
            return row[c]
    return ""


def flags_for(row):
    return {name: bool(pred(get(row, cands))) for name, cands, pred in FLAGS}


def build_master():
    """Union all run folders' eval_results (attempt_id key, latest run wins)."""
    master = {}
    for f in sorted(glob.glob(os.path.join(QA, "20*", "eval_results.csv"))):  # run folders sort by date
        for row in csv.DictReader(open(f)):
            aid = (row.get("attempt_id") or "").strip() or row.get("task_id")
            master[aid] = row  # later run overwrites earlier
    return master


def id_map():
    m = {}
    if os.path.exists(CANON):
        for row in csv.DictReader(open(CANON)):
            sb = (row.get("submitted by") or "").strip()
            if sb and sb not in m:
                m[sb] = (row.get("submitted by id") or "").strip()
    return m


def main():
    master = build_master()
    ids = id_map()
    # attempt-level master out
    os.makedirs(HIST, exist_ok=True)
    per = collections.defaultdict(list)  # attempter -> list of (rating, flags, country, date)
    with open(os.path.join(HIST, "all_attempts.csv"), "w", newline="") as f:
        cols = ["attempt_id", "task_id", "attempter", "attempt_date", "country", "rating"] + [n for n, _, _ in FLAGS]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for aid, row in master.items():
            fl = flags_for(row)
            att = (row.get("attempter_email") or "").strip()
            rec = {"attempt_id": aid, "task_id": row.get("task_id", ""), "attempter": att,
                   "attempt_date": (row.get("attempt_date") or "").strip(), "country": (row.get("country") or "").strip(),
                   "rating": (row.get("rating") or "").strip()}
            rec.update({n: int(fl[n]) for n, _, _ in FLAGS})
            w.writerow(rec)
            if att: per[att].append(rec)

    # per-attempter rollup. Each metric is emitted as RATE then N.
    ETYPES = [n for n, _, _ in FLAGS]
    OUTCOMES = [("no issues", "no_issues"), ("backfill", "backfill"),
                ("needs review", "needs_review"), ("needs to be wiped", "wiped")]
    out_cols = ["attempter", "attempter_id", "country", "n_attempts", "clean_rate", "quality_score"]
    out_cols += [f"{k}_rate" for _, k in OUTCOMES] + [f"{e}_rate" for e in ETYPES]   # all rates first
    out_cols += [f"n_{k}" for _, k in OUTCOMES] + [f"{e}_n" for e in ETYPES]         # then all counts
    rows = []
    for att, recs in per.items():
        n = len(recs)
        cat = collections.Counter(r["rating"] for r in recs)
        # adjusted quality weight (ignores uk_in_session)
        ws = []
        for r in recs:
            fset = {e for e in ETYPES if r[e]}
            if fset & WIPED: ws.append(0.0)
            elif fset & REVIEW: ws.append(0.2)
            elif fset & BACKFILL: ws.append(0.6)
            else: ws.append(1.0)
        country = collections.Counter(r["country"] for r in recs if r["country"]).most_common(1)
        row = {"attempter": att, "attempter_id": ids.get(att, ""),
               "country": country[0][0] if country else "",
               "n_attempts": n,
               "clean_rate": round(cat.get("no issues", 0) / n, 3),
               "quality_score": round(100 * statistics.mean(ws), 1)}
        for cat_name, k in OUTCOMES:
            c = cat.get(cat_name, 0)
            row[f"{k}_rate"] = round(c / n, 3); row[f"n_{k}"] = c
        for e in ETYPES:
            c = sum(r[e] for r in recs)
            row[f"{e}_rate"] = round(c / n, 3); row[f"{e}_n"] = c
        rows.append(row)
    rows.sort(key=lambda r: (-r["n_attempts"], r["quality_score"]))
    out = os.path.join(HIST, "contributor_quality.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([c.replace("_", " ") for c in out_cols])   # headers: lowercase, no underscores
        for r in rows:
            w.writerow([r.get(c, "") for c in out_cols])
    print(f"wrote {out} — {len(rows)} contributors from {len(master)} attempts")
    print(f"      {os.path.join(HIST,'all_attempts.csv')} — {len(master)} attempts (master)")


if __name__ == "__main__":
    main()
