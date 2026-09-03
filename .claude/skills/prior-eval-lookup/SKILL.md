---
name: prior-eval-lookup
description: Look up the most recent prior eval + feedback for a given attempt id or task id by scanning the run folders on disk (no history DB). Use for redos — to pull what a task's `initial attempt id` (or `L0 reviewed attempt id`) got last time, and to derive "changes since last eval." Also use when the user asks "what did we say about this task/attempt before?".
---

# Prior-eval lookup

The eval pipeline is still churning (columns/phase files change often), so there is deliberately **no
structured history DB**. Instead, this skill finds the most recent prior eval of an attempt/task by
scanning the run folders on disk — the live ones and the local archive.

Use it for **redos**: a redo carries `initial attempt id` (the first-eval attempt it's redoing) and, for
L10, `L0 reviewed attempt id` (the attempt the reviewer looked at). Look those up to get the last
category, drivers, and feedback — which is how you derive **"changes since last eval"** for the redo /
L10 tables without keeping history.

## How
```
python3 .claude/skills/prior-eval-lookup/find_prior_eval.py --attempt <attempt_id>
python3 .claude/skills/prior-eval-lookup/find_prior_eval.py --task <task_id> --all   # every run it appears in
```
It scans `qa_pipeline_active/20YY-MM-*` and the archive's run folders, matches by `attempt_id`
(from each run's `meta.json`) or `task_id`, and prints — newest run first — the run, level, our
category + drivers, and the reviewer-facing feedback (external / contributor) that run wrote.

## If the script finds nothing
The eval may have only been discussed in a session, not saved to a run folder. Fall back to grepping the
session transcripts:
```
grep -l "<attempt_or_task_id>" ~/.claude/projects/-Users-xilin-zhou-Documents-task-scraper/*.jsonl
```
and read the relevant lines. Given how few redos there are right now, one of these two will find it.

## Notes
- There should be **few** of these at the moment — a linear scan is fine; don't over-engineer.
- This is READ-ONLY — it never changes any eval output.
- When the eval schema stabilizes, this can be replaced by a real history store (deferred on purpose).
