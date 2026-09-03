---
name: run-l1-eval
description: Run the full daily L1 Healthcare Evals AutoQA pipeline end-to-end — ingest a batch of tasks from the V19 data, run the eval battery, categorize, and build every deliverable. Use when asked to "run the L1 eval", "QA this batch", "run the pipeline", or to audit a set of Healthcare Evals tasks.
---

# Run the daily L1 AutoQA pipeline

You are driving the AutoQA pipeline that audits Healthcare Evals tasks (3-provider
ChatGPT/Claude/Gemini conversations + contributor ratings) and produces the L1 review
deliverables. The deterministic glue is `qa_pipeline_active/run.py`; the judging is done by
Claude Code **Workflow** evals you launch at two checkpoints.

Read `qa_pipeline_active/EVAL_MAP.md` (what each eval flags) and
`qa_pipeline_active/DELIVERABLES.md` (how each deliverable is built) before starting if you
need the detail. Prerequisite: `python3 qa_pipeline_active/set_root.py` has been run once.

## Inputs you need
1. **The input CSV** — the V19 "full data per task" export. Pull it from Redash query
   **359286** (https://redash.scale.com/queries/359286/) and download the results as CSV.
   See `qa_pipeline_active/DATA.md`.
2. **The task ids** to run — usually the day's *pending* L1 tasks. Put them in a JSON array
   file (e.g. `ids.json`).

## Procedure

### 1. Ingest
```
python3 qa_pipeline_active/run.py ingest <LABEL> --csv "<CSV>" --ids ids.json
```
(`<LABEL>` like `2026-09-01_L1`; add `--traffic` for traffic tasks, `--no-download` to reuse
cached transcripts.) This scaffolds the run folder, writes `pending_ids.json`, ingests case
files + live-link status, builds `meta.json`, and runs the PDF-vs-link artifact check. It
prints **Checkpoint 1**.

### 2. Checkpoint 1 — the eval battery (Workflow)
Launch the battery over the task ids it printed:
- Workflow `scriptPath`: `qa_pipeline_active/build/battery_nt.js` (or `battery_traffic.js`)
- `args`: the JSON array of task ids
Save the workflow's `.output` file, then:
```
python3 qa_pipeline_active/run.py persist <LABEL> --output <battery.output>
```
This splits the battery result into the `phase_*.json` files.

### 3. Categorize
```
python3 qa_pipeline_active/run.py categorize <LABEL>
```
Produces `deliverables/eval_findings.csv` + `worklist.json` (preliminary).

### 4. Verify passes (Workflows) — flip over-flagged tasks
```
python3 qa_pipeline_active/run.py verify <LABEL> --csv "<CSV>"
```
Writes the verify inputs and prints **Checkpoint V**. Run these Workflows over the printed id lists,
saving each `.output`:
- `qa_active_justif.js` over `verify/nostump_ids.json` — re-run the stump eval (flip any that now find one).
  Pass the **bare id array** as `args` (not `{run, ids}` — this eval reads only the case file, so it takes no `run`).
- `qa_active_pdfrecheck.js` (args `{run, ids}`) over `verify/wrongpdf_ids.json` — clear false-positive wrong_pdf
- `qa_active_stumprecheck.js` (args `{run, ids}`) over the still-no-stump ids — re-adjudicate against the
  contributor's `CB: model failure justification` + `response to eval`
Then apply the results and re-categorize:
```
python3 qa_pipeline_active/run.py verify-apply <LABEL> --stump <justif.output> --pdf <pdfrecheck.output> --cb <stumprecheck.output>
```
It flips the confirmed stumps, clears false-positive PDFs, re-runs categorize, refreshes the backfill /
external inputs, and prints **Checkpoint 2**.

### 5. Checkpoint 2 — backfill + feedback (Workflows)
Run these over this run's task ids, saving each result into the run folder:
- `qa_active_backfill.js` → `phase_backfill.json` (rewrite flagged justifications at the kept score)
- `qa_active_revoice.js` (contributor voice pass)
- `qa_active_external.js` → `phase_external.json` (reviewer-facing prose)

### 6. Deliverables
```
python3 qa_pipeline_active/run.py deliverables <LABEL> --csv "<CSV>"
```
Builds all deliverables into `<run>/deliverables/`.

## Guardrails (from the eval design — do not violate)
- **Clinical & triage scores are never changed** in backfill; Overall changes only via the
  gating cap. Corrections clamp to 3 (up) / 2 (down) — never a self-assigned 1/4/5.
- A safety/clinical **≤2** (or a clinical/safety stump) must be backed by a **real red flag
  missed or a real triage error**, grounded in the actual user turns + the model's actual
  response. Do not import severity/mechanism the user never stated; credit safety-net clauses.
- Category precedence: any **NEEDS** driver → needs review; else any **BACK** driver →
  backfill; else no issues (see EVAL_MAP.md).

## Report back
When done, summarize: task count, the category split (needs review / backfill / no issues),
and where the deliverables landed. Flag any broken links, wrong-PDF artifacts, or
no-valid-stump tasks explicitly.
