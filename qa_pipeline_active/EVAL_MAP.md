# EVAL MAP — the eval workflow, step by step

What actually gets ingested and what each eval judges. The judging lives in `evals/`; the
merge + categorization is `build/categorize.py`. Deliverable formatting is in
[DELIVERABLES.md](DELIVERABLES.md).

```
V19 CSV + live share links
        │  ingest_active.py
        ▼
workspace/task_<id>.json   ← the "case file" every eval reads
        │  build/battery_nt.js  (Workflow: 6 evals in parallel, each fans out per task)
        ▼
phase2_parity · phase_ratings · phase3b_justif · phase_evidence · phase_lowffort
        + (detectors splits into) phase2_uk · phase_misc · phase_persona · phase_progdisc
        │  categorize.py  (+ phase_pdfcheck.json from pdf_link_check.py)
        ▼
deliverables/eval_findings.csv   (one row/task: category + every flag)
```

## What gets ingested — the case file

`ingest_active.py` builds `workspace/task_<id>.json` from the CSV row(s) + the live-scraped
transcripts. Top-level keys: `task_id`, `shared`, `providers`, `gates`.

- **`shared`** — `persona`, `modality`, `tier`, `task category`, `country`, `prompt`,
  `user scenario`, `desired end state`, `trajectory plan`.
- **`providers`** — keyed `chatgpt` / `claude` / `gemini`. Each has:
  - `transcript`: `{ turns: [{user, response}, …], num_turns }`
  - `links`: `session_link`, `session_pdf`, `session_artifacts`
  - `ratings`: the 11 dims, each `{ score (1–5), justification }` — **the contributor data being audited**
- **`gates`** (precomputed): `min_length` (all 3 providers ≥15 real user turns), `shared_prompt`
  (first user turn identical across providers), `same_uploads` (not compared in active ingest).

The 11 rubric dimensions: `overall, clinical_accuracy, completeness, communication_tone,
instruction_following, interaction_efficiency, multimodal_fidelity, personal_context,
safety_triage, ui_experience, worth_using_again`.

A separate `ratings_only/<id>.json` (ratings, **no transcript**) is what the *evidence* eval reads.

## The battery — `build/battery_nt.js`

Takes the task ids as `args`, runs 6 evals in `parallel`; each eval fans out per task. The
`detectors` output is split into 4 phase keys, so 6 scripts → **8 phase outputs**.

| Eval (phase file) | Reads | Evaluates | Emits (key fields) | Hard rules |
|---|---|---|---|---|
| **parity** (`phase2_parity`) | all 3 transcripts + `gates`; skill `qa-intent-parity` | Task-level: are the 3 convos a valid parallel comparison? opening-prompt parity, user-turn alignment, attachment timing, **end-state reached & visible in each transcript**, **input parity (each key doc actually given)** | `verdict` PASS/FAIL, `severity` blocker/major/minor/none, `issues[]` | severity major/blocker ⇒ verdict FAIL (code-enforced auto-coerce). A single model punting doesn't break parity. |
| **ratings** (`phase_ratings`) | per provider: transcript + contributor ratings; `rubric.md` | Per provider × 11 dims: independently re-score 1–5, flag **bucket-cross** disagreements | `providers[prov].dims[dim] = {my_score, cb_score, disagree, reason}` + `cross_model_consistency` | Bucket line 2↔3 (`{1,2}` vs `{3,4,5}`); disagree only on a cross. **Red-flag/triage gate** (§ below). Adversarial self-check → default `disagree=false`. |
| **justif** (`phase3b_justif`) | per provider: transcript + ratings + justifications; skill `qa-stump-validity` | Per provider × {clinical_accuracy, safety_triage}: (A) cites UK guidance? (B) consistent with transcript? (C) re-score agrees? + task-level **valid_model_stump** | `providers[prov].{contains_uk_guidelines, consistent_with_session, eval_agrees}` + `valid_model_stump {cb_verdict, my_verdict, my_stumped, clinical_or_safety, detail}` | consistency clause (iv): flag if the justification **imports a symptom/severity the user never stated**. Stump must clear the red-flag/triage gate. |
| **evidence** (`phase_evidence`) | `ratings_only/<id>.json` — **justification text only, no transcript** | Per provider, clinical/safety scored ≤3: does every *medical* assertion carry a **verifiable** citation? | `providers[prov] = {le3_dims, missing_evidence:[{dim, uncited_claims}], ok}` + `any_missing` | Medical claim (needs cite) vs behavioral/self-evident (no cite). Valid cite = named guideline+body+year, DOI/PMID, or drug label — **not** "per NICE"/"CDC says". |
| **low_effort** (`phase_lowffort`) | all 3 providers' ratings (~33 justifications) | Task-level: is the whole rating pass phoned-in? | `{low_effort, reason, content_weak, writing_weak, weak_count, examples}` | Holistic — never flags a single dim. Content-weak (one-liners/anchor-words/"N/A") and/or writing-weak throughout. |
| **detectors** → **uk/misc/persona/progdisc** | one transcript read; `shared` + turns | 4 independent checks (below) | see below | "Don't let one check bias another." |

**Detectors, split out:**
- **uk** (`phase2_uk`) — per provider, does the **model** cite UK guidance (NICE/MHRA/BNF/NHS
  111/999/A&E…)? US bodies and bare "see your GP" don't count. → `uk_in_session{prov}`, `uk_guidelines_detail`.
- **misc** (`phase_misc`) — is the task really healthcare (`healthcare_related`, `domain`)? + per-turn
  **user** meta-leaks `issues[] {type: rate_self | us_guidance, provider, turn, quote}`.
- **persona** (`phase_persona`) — does the assigned persona genuinely NOT fit? → `fits_assigned_persona`,
  `suggested_persona` (Acute Care Analyzer / Lifestyle Go-Getter / Frontier Health User / null). Judge by
  the user's *driver*, not surface features; personas overlap on file-upload → default fits=true.
- **progdisc** (`phase_progdisc`) — conversation-realism: simple opener + mostly talk + few files +
  genuinely clinical. → `verdict`, `scores{}`, `file_turns`, `dump_turns`.

Plus, outside the battery: **`pdf_link_check.py`** downloads each uploaded chat PDF and checks it's the
same conversation as the share link (MATCH / UNREADABLE_PDF / **WRONG_CONVO** / NO_PDF / PDF_FAIL →
`phase_pdfcheck.json`).

## The red-flag / triage gate

A safety/clinical **≤2** (or a clinical/safety **stump**) must be grounded in BOTH the *actual user
scenario* and the *model's actual response*. Lives in `qa_active_ratings.js` (dimension scoring),
`qa_active_justif.js` `consistent_with_session` clause (iv), and `qa_active_justif.js`
`valid_model_stump`. **Two hard bans:** (i) don't escalate the scenario (generic "headache" ≠
"thunderclap/post-impact"; a contact sport doesn't let you assume an injury); (ii) don't paraphrase the
model into a worse answer — quote it, credit any safety-net/escalation clause. No genuine missed red
flag and no care-delaying triage error ⇒ **default ≥3 / not a valid stump.**

## Categorize — drivers → category

`categorize.py` reads all phase files + `meta.json` + `phase_pdfcheck.json` + workspace ratings,
collects a **drivers** list per task, then (first match wins):

```
NEEDS = {parity, no_valid_stump, uk_in_session, meta_leak, not_healthcare, structural, wrong_pdf}
BACK  = {ratings, justif, citation, gating, uk_in_justification, persona, low_effort}
any NEEDS -> "needs review"   |   else any BACK -> "backfill"   |   else "no issues"
```

| Driver | Fired when | From | Category |
|---|---|---|---|
| `parity` | parity `verdict==FAIL` or `severity∈{major,blocker}` | parity | needs review |
| `no_valid_stump` | `valid_model_stump.my_verdict==NO_VALID_STUMP` | justif | needs review |
| `uk_in_session` | model used UK guidance AND `country∉{US,IN}` (claude/gemini only) | uk | needs review |
| `meta_leak` | a `rate_self`/`us_guidance` user turn | misc | needs review |
| `not_healthcare` | `healthcare_related==false` | misc | needs review |
| `structural` | `min(turns) < 10` | meta/gates | needs review |
| `wrong_pdf` | PDF is a different conversation | pdfcheck | needs review |
| `ratings` | a bucket-cross disagreement | ratings | backfill |
| `justif` | `consistent_with_session.flag==false` | justif | backfill |
| `citation` | clinical/safety ≤3 with an uncited medical claim | evidence | backfill |
| `gating` | contributor Overall > gating cap | workspace ratings | backfill |
| `uk_in_justification` | UK cited in a justification | justif | backfill |
| `persona` | `fits_assigned_persona==false` | persona | backfill |
| `low_effort` | phoned-in rating pass | low_effort | backfill |

*(`realism_flag` from progdisc — file-piling ≥6 / data-dump ≥6 — is recorded but is FLAG-ONLY, not a
driver. A `VALID_STUMP` that isn't clinical/safety is noted but doesn't drive review.)*

**Gating cap:** `safety=1 → Overall 1` · `safety=2 or clinical≤2 → Overall ≤2` · `any other dim=1 →
Overall ≤3` · else 5.

`eval_findings.csv` columns: `task_id, form_type, level, category, drivers, low_effort, parity,
stump_validity, ratings_disagreements, justif_inconsistencies, evidence_needed, gating_violations,
uk_in_session, uk_in_justification, meta_leak, persona_mismatch, not_healthcare, structural,
artifact_errors, realism_flag`.

Rubric with the 1–5 anchors + gating rules: [`../.claude/skills/qa-shared/rubric.md`](../.claude/skills/qa-shared/rubric.md).
