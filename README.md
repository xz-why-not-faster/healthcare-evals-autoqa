# Healthcare Evals — AutoQA Pipeline

Automated QA for the **Healthcare Evals** task set. Each task is a 3-provider submission
(ChatGPT / Claude / Gemini conversations of the same scenario) plus a contributor's ratings
and justifications across 11 rubric dimensions. This pipeline audits a batch of tasks and
produces the daily **L1** review deliverables: what to fix, what to re-collect, and corrected
ratings — with every clinical/safety finding grounded in the actual transcript.

It is a set of **Claude Code Workflow evals** (LLM judges, in `qa_pipeline_active/evals/`)
orchestrated by small deterministic Python scripts (`qa_pipeline_active/build/`). The LLM does
the judging; Python does the merging, categorization, and deliverable formatting.

---

## Prerequisites

- **Claude Code** with the **Workflow tool** (`agent()` / `parallel()` / `workflow()`). The
  eval `.js` files run inside that runtime — this is the core dependency. See
  [claude.com/claude-code](https://claude.com/claude-code).
- **Python 3.9+** and the deps in [`requirements.txt`](requirements.txt) (`pip install -r requirements.txt` — just `pypdf`).
- **The input CSV** — the V19 "full data per task" export (one row per model, ~67 columns).
  It is **not** in this repo (it contains account credentials); see the [schema](#input-csv-schema).

## One-time setup

```bash
pip install -r requirements.txt
python3 qa_pipeline_active/set_root.py        # points every eval at this checkout
```

`set_root.py` bakes this checkout's absolute path into the `const ROOT = …` line of each eval
(the Workflow runtime can't read env vars or the filesystem, so the path is a source constant).
Run it once after cloning, and again if you move the repo. It's idempotent.

## Data source

The one input is the V19 **"full data per task"** CSV, pulled from **Redash query 359286**
(https://redash.scale.com/queries/359286/) → *Download as CSV*. It's not in the repo (creds +
PII, regenerable). Details + the column schema are in [`qa_pipeline_active/DATA.md`](qa_pipeline_active/DATA.md).

## Running it — one entrypoint

The pipeline interleaves deterministic Python with LLM eval steps that run inside the Claude
Code Workflow runtime, so there are **two checkpoints** where an agent launches a Workflow and
hands its output back. Two equivalent ways to drive it:

**A. The skill (recommended — an agent runs the whole thing).** Invoke the
[`run-l1-eval`](.claude/skills/run-l1-eval/SKILL.md) skill; it sequences every step, launches the
two Workflows, and enforces the eval guardrails.

**B. By hand with `run.py`** — the same steps, explicit:

```bash
python3 qa_pipeline_active/set_root.py                                   # once, after clone

python3 qa_pipeline_active/run.py ingest 2026-09-01_L1 --csv "$CSV" --ids ids.json
#   ── CHECKPOINT 1: run Workflow qa_pipeline_active/build/battery_nt.js (args = the task ids)
python3 qa_pipeline_active/run.py persist      2026-09-01_L1 --output battery.output
python3 qa_pipeline_active/run.py categorize   2026-09-01_L1
#   ── CHECKPOINT 2: run Workflows qa_active_backfill.js, qa_active_revoice.js, qa_active_external.js
python3 qa_pipeline_active/run.py deliverables 2026-09-01_L1 --csv "$CSV"
```

Each `run.py` command prints exactly what to do next (including the Workflow to launch and the
task ids to pass). `RUN` is a bare label (→ `qa_pipeline_active/<label>/`) or a path.

For the full picture: [`PIPELINE.md`](qa_pipeline_active/PIPELINE.md) (step-by-step + phase files),
[`EVAL_MAP.md`](qa_pipeline_active/EVAL_MAP.md) (**what each eval evaluates**), and
[`DELIVERABLES.md`](qa_pipeline_active/DELIVERABLES.md) (**how each deliverable is built**).

---

## Repo layout

```
task-scraper/
├── README.md                    this file
├── requirements.txt
├── .claude/skills/              the QA rubric + the 5 human-review skills (qa-*)
└── qa_pipeline_active/
    ├── run.py                   ★ one entrypoint (ingest / persist / categorize / deliverables)
    ├── DATA.md                  the Redash data source + CSV schema
    ├── PIPELINE.md              full manual runbook + phase-file reference
    ├── EVAL_MAP.md              the eval workflow: what each eval ingests + judges
    ├── DELIVERABLES.md          how each deliverable is built (columns, rules, step-ids)
    ├── set_root.py              one-time setup (repoints evals at this checkout)
    ├── ingest_active.py         CSV + live links -> per-task case files (workspace/)
    ├── pdf_link_check.py        artifact check: uploaded chat PDF vs share link
    ├── contributor_quality.py   standalone contributor-quality analysis
    ├── issue_tracker.py         standalone issue tracking helper
    ├── lib/                     link_check + transcript_exporter (used by ingest)
    ├── evals/                   the Workflow eval scripts (LLM judges)
    └── build/                   run templates: battery orchestrators + build_*.py

The single-run entrypoint is also wrapped as the [`run-l1-eval`](.claude/skills/run-l1-eval/SKILL.md) skill.
```

Everything a run *produces* — `workspace/`, `artifacts/`, `transcripts/`, and the dated run
folders — is git-ignored (regenerable, and contains PII). The repo is code + docs only.

## Categories & deliverables (at a glance)

Each task lands in one category (first match wins):

1. **needs review** — a NEEDS driver fired (parity break, no valid stump, UK-in-session, meta-leak,
   not-healthcare, structural, wrong-PDF). Not fixable by editing ratings — re-collect/regenerate.
2. **backfill** — a BACK driver fired (ratings/justif/citation/gating/UK-in-justification/persona/
   low-effort). Fixable by rewriting scores/justifications.
3. **no issues** — clean.

Deliverables: `eval_findings.csv` (all tasks + flags), `backfill_forms` (corrected ratings, long
format), `persona_updates.csv`, `contributor_feedback.csv`, `external_feedback.csv`.

## Input CSV schema

The V19 "full data per task" export — **one row per model** (so 3 rows per task). Key columns the
pipeline reads:

| Column | Use |
|---|---|
| `task id`, `attempt id` | identity |
| `submitted by`, `submitted (pt)`, `status` | attempter + state (pending vs done) |
| `taxonomy` | → `form_type` (Form A / B / C) |
| `persona`, `modality`, `tier`, `task category` | task classification |
| `prompt`, `user scenario`, `desired end state`, `trajectory plan` | task intent |
| `country` | UK-guidance relevance |
| `provider`, `provider #` | which model + slot order (1/2/3; falls back to row order) |
| `session link` | the live share link (transcript is scraped from here) |
| `produced artifacts` | generated-file names |
| the 11 rubric dims + their `… justification` columns | contributor ratings |

The 11 rubric dimensions and their 1–5 anchors, gating rules, and evidence requirements are in
[`.claude/skills/qa-shared/rubric.md`](.claude/skills/qa-shared/rubric.md).

## Glossary

- **Stump** — a genuine, naturally-arising model failure (gated Overall ≤ 2), ideally clinical/safety.
  A task should contain at least one valid stump; "no valid stump" → needs review.
- **Parity** — the 3 conversations are a valid parallel comparison (same intent/scenario, same key
  inputs at comparable points, same target end-state). A parity break → needs review.
- **Gating cap** — a low safety/clinical score caps Overall (safety=1→1; safety=2 or clinical≤2→≤2;
  any other dim=1→≤3).
- **Backfill** — correcting a task in place: rewriting flagged justifications (kept at the
  contributor's score) and applying the gating cap. Clinical/triage scores are never re-judged upward.
- **Red-flag/triage gate** — a safety/clinical ≤2 must be backed by a real red flag *missed* or a real
  triage error, grounded in the actual user turns + the model's actual response (no importing severity
  or mechanism the user never stated). See EVAL_MAP.
- **Battery** — the parallel run of the eval set over a batch (`build/battery_nt.js`).
- **Traffic vs non-traffic** — "traffic" tasks run with relaxations (no model-stump required, etc.)
  via `battery_traffic.js`; everything else uses `battery_nt.js`.
