# QA Active Pipeline — full runbook

End-to-end auto-QA over the V19 "full data per task" sheet for the daily **L1** review. The eval
judging is done by Claude Code **Workflow** scripts in `evals/`; small deterministic Python scripts
in `build/` merge the results, categorize each task, and format the deliverables.

> **Prerequisite:** run `python3 set_root.py` once after cloning (see [README](../README.md)).

## Run-folder model

Everything for one run lives in a dated folder directly under `qa_pipeline_active/`, e.g.
`qa_pipeline_active/2026-09-01_L1/`. The `build/*.py` scripts resolve their inputs **relative to
their own location** (`RUN = dirname(__file__)`, `WS = RUN/../workspace`), so each run begins by
copying the templates in:

```bash
cd qa_pipeline_active
RUN=2026-09-01_L1
mkdir -p "$RUN" && cp build/* "$RUN"/
```

That folder then accumulates: `meta.json`, the `phase_*.json` eval outputs, `worklist.json`,
`external_input/`, and finally `deliverables/`.

Shared (not per-run) data lives one level up in `qa_pipeline_active/`:

```
workspace/task_<id>.json   per-task case file (metadata + ratings + scraped transcripts)
artifacts/<tid>/<prov>/     downloaded generated artifacts
transcripts/                live-scraped transcript cache
```

## Steps

### 0. Inputs
- **CSV** — the V19 "full data per task" export (one row per model). Columns the pipeline reads are
  listed in the [README schema](../README.md#input-csv-schema).
- **Task ids** — a JSON array of the task ids to run (e.g. `ids.json`). Typically the *pending* L1
  tasks for the day.

### 1. Ingest → case files
```bash
python3 ingest_active.py --csv "$CSV" --run "$RUN" --levels L1 --tasks-file "$RUN/ids.json"
python3 "$RUN"/build_meta.py "$CSV"     # -> $RUN/meta.json
```
`ingest_active.py` builds `workspace/task_<id>.json` (metadata + the 11-dim ratings from the CSV +
the live transcripts), scrapes each `session link` (unless `--no-download`), and writes
`turns_summary.json` (per-provider link status: WORKING / DELETED / NOT_PUBLIC / EMPTY_OR_BLOCKED /
NO_URL) and `sheet_tasks.json`. Flags: `--tasks`/`--tasks-file`, `--no-download`, `--include-bot`
(include `scale@scale.com` attempts, normally skipped), `--levels`.

`build_meta.py` emits per-task `form_type`, `country`, provider order, persona, links, and turn
counts. Pass the CSV as arg1 (or set `QA_INPUT_CSV`).

### 2. Artifact check (standard)
```bash
python3 pdf_link_check.py "$RUN"        # -> $RUN/phase_pdfcheck.json
```
Downloads each provider's uploaded `session_pdf`, extracts its text, and checks it's the **same
conversation** as the live share link. Verdicts: MATCH / UNREADABLE_PDF / WRONG_CONVO / NO_PDF /
PDF_FAIL. A `WRONG_CONVO` sets `task_artifact_pdf_issue` → drives `wrong_pdf` → **needs review**.

### 3. The eval battery (Workflow)
Run `build/battery_nt.js` (non-traffic) or `build/battery_traffic.js` (traffic) with the task ids
as `args`. The battery fans out these evals in parallel:

| battery key | eval file | produces |
|---|---|---|
| parity | `qa_active_parity.js` | 3-way parallel-comparison validity |
| ratings | `qa_active_ratings.js` | independent re-score (bucket-cross disagreements) |
| justif | `qa_active_justif.js` | justification ↔ transcript consistency + `valid_model_stump` |
| evidence | `qa_active_evidence.js` | clinical/safety ≤3 needs a verifiable citation |
| low_effort | `qa_active_lowffort.js` | task-level phoned-in rating pass |
| detectors | `qa_active_detectors.js` | **uk + misc + persona + progdisc** in one transcript read |

Save the workflow's `.output`, then split it into phase files:
```bash
python3 "$RUN"/persist_battery.py <battery.output>
```
→ `phase2_parity.json`, `phase_ratings.json`, `phase3b_justif.json`, `phase_evidence.json`,
`phase_lowffort.json`, and (from detectors) `phase2_uk.json`, `phase_misc.json`, `phase_persona.json`,
`phase_progdisc.json`.

### 4. Categorize
```bash
python3 "$RUN"/categorize.py            # -> deliverables/eval_findings.csv, worklist.json
```
Merges all phase files + `meta.json` + `phase_pdfcheck.json` + workspace ratings into one row per
task with a `category` and the firing `drivers`. See [EVAL_MAP.md](EVAL_MAP.md) for the driver→
category rules. `eval_findings.csv` columns: `task_id, form_type, level, category, drivers,
low_effort, parity, stump_validity, ratings_disagreements, justif_inconsistencies, evidence_needed,
gating_violations, uk_in_session, uk_in_justification, meta_leak, persona_mismatch, not_healthcare,
structural, artifact_errors, realism_flag`.

### 5. Backfill (Workflow)
For **backfill**-category tasks only:
```bash
python3 "$RUN"/build_worklist.py        # per-provider orig scores + per-dim {target, needs_rewrite}
```
Then run `qa_active_backfill.js` (rewrites flagged justifications at the kept score, folds in
verifiable citations) → `phase_backfill.json`, and `qa_active_revoice.js` (puts them in the
contributor's voice). Rules: clinical/triage scores are **never** changed; Overall changes **only**
via the gating cap; corrections clamp to 3 (up) / 2 (down), never a self-assigned 1/4/5.

### 6. External + contributor feedback (Workflow)
```bash
python3 "$RUN"/build_external_input.py  # external_input/<tid>.json for needs-review tasks
```
Run `qa_active_external.js` to rewrite findings into concise reviewer-facing prose →
`phase_external.json`.

### 7. Deliverables
```bash
python3 "$RUN"/build_melt.py                 # backfill_forms — long format: task, step, value
python3 "$RUN"/build_persona_sheet.py        # persona_updates.csv (wide, one row per correction)
python3 "$RUN"/build_contributor_feedback.py # contributor_feedback.csv (parity / broken-link only)
python3 "$RUN"/build_sheets.py "$CSV"        # external_feedback.csv
python3 "$RUN"/build_disagreements.py        # ratings-disagreement inspection sheet (optional)
```
All land in `$RUN/deliverables/`.

## Re-running a single eval
Re-run its Workflow into the run folder and re-persist just that phase (or re-run
`build/rerun_justif.js` / `build/rerun_rj.js` for the ratings/justif pair), then re-run
`categorize.py` and the relevant `build_*` steps. The Python builders are deterministic — rule-only
changes need no re-eval, just re-run the builders over the existing phase files.

## Notes
- **Stump-verdict non-determinism:** borderline stump calls can flip ~50% on re-run. For a contested
  task, re-run `justif` a couple of times and take the consistent verdict.
- **Gating cap from corrected dims:** `build_worklist.py` recomputes the Overall gating cap from the
  *corrected* dimensions (post-pass), so a corrected clinical/safety cascades to Overall.
