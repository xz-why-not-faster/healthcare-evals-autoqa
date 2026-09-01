#!/usr/bin/env python3
"""
merge_journal.py — turn a workflow's journal.jsonl into a {task_id: result} phase JSON.

Each eval workflow emits one structured result per task ({"task_id": ..., ...}); this
collapses them into the {task_id: result} shape that build_eval_results.py reads.

Usage: merge_journal.py <wf_run_dir_or_journal.jsonl> <out_phase.json>
"""
import json, os, sys

src = sys.argv[1]
out = sys.argv[2]
journal = src if src.endswith(".jsonl") else os.path.join(src, "journal.jsonl")

# merge INTO any existing phase file (don't clobber a larger set with a small batch)
merged = json.load(open(out)) if os.path.exists(out) else {}
for line in open(journal):
    line = line.strip()
    if not line:
        continue
    rec = json.loads(line)
    if rec.get("type") != "result":
        continue
    res = rec.get("result")
    if isinstance(res, dict) and res.get("task_id"):
        merged[res["task_id"]] = res

json.dump(merged, open(out, "w"), indent=1, ensure_ascii=False)
print(f"wrote {out} — {len(merged)} tasks")
