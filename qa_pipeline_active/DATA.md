# Data source — the V19 input CSV

The pipeline's single input is the V19 **"full data per task"** export: one row per model
(so 3 rows per task), carrying the task metadata, the live share links, and the contributor's
11-dimension ratings + justifications.

## Where it comes from

Redash query **359286** — https://redash.scale.com/queries/359286/

Run the query for the batch you want to QA, then **Download → Download as CSV**. That CSV is
the `--csv` argument to every `run.py` step. It is **not** checked into this repo (it contains
account credentials and contributor PII, and is fully regenerable from Redash); `.gitignore`
blocks `*.csv`.

## Columns the pipeline reads

| Column | Used for |
|---|---|
| `task id`, `attempt id` | task/attempt identity (a changed attempt id = contributor redid it) |
| `submitted by`, `submitted (pt)`, `status` | attempter, timestamp, pending-vs-done state |
| `taxonomy` | → `form_type` (Form A / B / C), which sets the deliverable step-ids |
| `persona`, `modality`, `tier`, `task category` | task classification |
| `prompt`, `user scenario`, `desired end state`, `trajectory plan` | task intent (parity, stump, categorization) |
| `country` | UK-guidance relevance (a non-US task citing UK guidance → flag) |
| `provider`, `provider #` | which model + slot order 1/2/3 (falls back to row order if `provider #` blank) |
| `session link` | the live share link — the transcript is scraped from here |
| `produced artifacts` | generated-file names (artifact checks) |
| the 11 rubric dims + each `… justification` | the contributor ratings being audited |

## Selecting tasks

You typically QA the day's **pending L1** tasks. Filter the ids however you like (from the
Redash result, a status column, or a hand-picked list) and pass them to `run.py ingest` via
`--ids ids.json` (a JSON array) or `--tasks id1,id2`.

The 11 rubric dimensions, their 1–5 anchors, gating rules, and evidence requirements are in
[`../.claude/skills/qa-shared/rubric.md`](../.claude/skills/qa-shared/rubric.md).
