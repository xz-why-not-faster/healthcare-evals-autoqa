#!/usr/bin/env python3
"""
issue_tracker.py — focus on the SERIOUS bucket: attempts that end up "needs review" or
"needs to be wiped" (the ones that need recollection / human fix, not a cheap backfill).

Answers: who are the top offenders, and what issue types drive review/wipe.
Reads eval_history/all_attempts.csv (the accumulating master built by contributor_quality.py).
Writes eval_history/issue_tracker.csv (one row per attempter, serious-issue focused) and prints
a cohort-level "what's driving it" summary.
"""
import csv, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QA = os.path.join(ROOT, "qa_pipeline_active")
HIST = os.path.join(ROOT, "eval_history")
MASTER = os.path.join(HIST, "all_attempts.csv")
CANON = os.path.join(QA, "V19_ AutoQA Setup - full data per task.csv")

# the only issue types that CAUSE needs-review or wipe (the serious bucket)
DRIVERS = [("broken_link", "wipe"), ("parity_fail", "review"), ("uk_in_session", "review"),
           ("no_valid_stump", "review"), ("safety_punt", "review"), ("artifact_issue", "review")]
DNAMES = [d for d, _ in DRIVERS]
SERIOUS = {"needs review", "needs to be wiped"}


def id_map():
    m = {}
    if os.path.exists(CANON):
        for row in csv.DictReader(open(CANON)):
            sb = (row.get("submitted by") or "").strip()
            if sb and sb not in m:
                m[sb] = (row.get("submitted by id") or "").strip()
    return m


def main():
    if not os.path.exists(MASTER):
        raise SystemExit("run contributor_quality.py first to build all_attempts.csv")
    attempts = list(csv.DictReader(open(MASTER)))
    ids = id_map()
    per = collections.defaultdict(list)
    for a in attempts:
        if a["attempter"]:
            per[a["attempter"]].append(a)

    total_serious = sum(1 for a in attempts if a["rating"] in SERIOUS)

    # ---- per-contributor rows (rates first, then counts) ----
    hdr = (["attempter", "attempter id", "country", "n attempts",
            "serious rate", "needs review rate", "wiped rate"] + [f"{d} rate" for d in DNAMES]
           + ["serious n", "n needs review", "n wiped"] + [f"{d} n" for d in DNAMES])
    rows = []
    for att, recs in per.items():
        n = len(recs)
        nr = sum(1 for a in recs if a["rating"] == "needs review")
        wp = sum(1 for a in recs if a["rating"] == "needs to be wiped")
        ser = nr + wp
        country = collections.Counter(a["country"] for a in recs if a["country"]).most_common(1)
        r = {"attempter": att, "attempter id": ids.get(att, ""),
             "country": country[0][0] if country else "", "n attempts": n,
             "serious rate": round(ser / n, 3), "needs review rate": round(nr / n, 3),
             "wiped rate": round(wp / n, 3), "serious n": ser, "n needs review": nr, "n wiped": wp}
        for d in DNAMES:
            c = sum(int(a.get(d, 0) or 0) for a in recs)
            r[f"{d} rate"] = round(c / n, 3); r[f"{d} n"] = c
        rows.append(r)
    rows.sort(key=lambda r: (-r["serious n"], -r["serious rate"]))
    out = os.path.join(HIST, "issue_tracker.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(hdr)
        for r in rows:
            w.writerow([r.get(c, "") for c in hdr])

    # ---- cohort "what's driving it" ----
    print(f"=== what's driving needs-review / wipe ({total_serious} serious attempts of {len(attempts)}) ===")
    print(f"{'issue':18} {'tier':7} {'n':>4} {'% of serious':>12}  top offender")
    drv = []
    for d, tier in DRIVERS:
        holders = [(a["attempter"], a) for a in attempts if int(a.get(d, 0) or 0)]
        n = len(holders)
        by = collections.Counter(h for h, _ in holders)
        top = by.most_common(1)
        drv.append((n, d, tier, top[0] if top else ("—", 0)))
    for n, d, tier, (who, c) in sorted(drv, reverse=True):
        share = f"{100*n/total_serious:.0f}%" if total_serious else "—"
        print(f"{d:18} {tier:7} {n:>4} {share:>12}  {who} ({c})")
    print(f"\ntop offenders by serious count (see {os.path.relpath(out, ROOT)}):")
    for r in rows[:10]:
        drivers = ", ".join(f"{d}×{r[f'{d} n']}" for d in DNAMES if r[f"{d} n"]) or "—"
        print(f"  {r['attempter'][:32]:33} {r['country'] or '—':3} n={r['n attempts']:>2}  serious={r['serious n']} ({r['serious rate']*100:.0f}%)  {drivers}")


if __name__ == "__main__":
    main()
