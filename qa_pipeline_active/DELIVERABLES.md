# DELIVERABLES — how each output is built

Every deliverable lands in `<run>/deliverables/`. They are built by deterministic Python over the
`phase_*.json` eval outputs + `meta.json` + `worklist.json` + the workspace ratings. This doc is the
spec for *what each one contains and how it's derived* — the part that's easy to get subtly wrong.

## Build order (and why it matters)

```
categorize.py            → deliverables/eval_findings.csv  + worklist.json (preliminary)
build_worklist.py        → worklist.json  (OVERWRITES: full 11-dim orig/fixes plan)
── run the backfill/revoice/external Workflows → phase_backfill.json, phase_external.json ──
build_melt.py            → deliverables/backfill_melt.csv
build_persona_sheet.py   → deliverables/persona_updates.csv
build_contributor_feedback.py → deliverables/contributor_feedback.csv (+ contributor_feedback_ids.json)
build_disagreements.py   → deliverables/ratings_disagreements.csv
build_sheets.py CSV      → deliverables/external_feedback.csv + backfill_forms.csv  (filters findings to L1 IN PLACE)
```

Two ordering constraints:
1. **`build_worklist.py` overwrites** the preliminary `worklist.json` that `categorize.py` wrote, with
   the full plan (all 11 dims, `orig` + `fixes`). Everything downstream reads the overwritten one.
2. **`build_sheets.py` rewrites `eval_findings.csv` filtered to L1 in place.** Any L10-consuming step
   must run *before* it. It also reads `contributor_feedback_ids.json`, so
   `build_contributor_feedback.py` must run first.

## The correction rules (shared across builders)

- **Gating cap:** `safety=1 → 1` · `safety=2 or clinical≤2 → 2` · `any other dim=1 → 3` · else `5`.
- **Score clamp:** a corrected rating moves **up to 3** or **down to 2** only —
  `3 if (cb≤2 and my≥3)`, `2 if (cb≥3 and my≤2)`, else keep `my`. **Never a self-assigned 1/4/5.**
- **Clinical & triage scores are never re-judged upward**; the contributor's original stands unless a
  bucket-cross disagreement clamps it, and Overall only moves via the gating cap.

---

## 1. `worklist.json` — the backfill plan (`build_worklist.py`)

**Scope:** tasks with `category=='backfill'`, all providers, **all 11 dims**.

**Per dim, decide `needs_rewrite` + `target_score`:**
- **ratings** — on a bucket-cross disagreement, `target = clamp(my)` (up-to-3/down-to-2).
- **justif** — `consistent_with_session.flag==false` → rewrite, reason `justif inconsistent`.
- **UK-in-justification** → rewrite, reason `reframe to US`.
- **evidence** — a `missing_evidence` item matching the dim → rewrite, reason `citation needed`; and if
  `dim ∈ {clinical_accuracy, safety_triage}` and `target≤3`, appends the requirement to cite **every**
  factual medical claim inline (drug label / named guideline+year / DOI-PMID) or soften/drop it.
- **overall gating** — first pass caps overall to `gating_cap(orig)`.
- **POST-PASS gating recompute** — recomputes the cap from the **corrected** dim scores and, if the
  corrected overall still exceeds it, forces `overall.needs_rewrite=True, target=newcap`. This is what
  cascades a corrected clinical/safety down into Overall.

**Output:** `{task: {providers: {prov: {orig:{dim:{score,justification}}, fixes:{dim:{needs_rewrite,
target_score,reasons}}}}, drivers}}`.

---

## 2. `backfill_melt.csv` — corrected ratings, LONG format (`build_melt.py`)

**Scope:** worklist (backfill only); emits **only dims with `needs_rewrite`**. Persona rows are
disabled here (they live in `persona_updates.csv`).

**Columns:** `task, step, value` — two rows per rewritten dim:
- rating row → `step = "{stepid}.{base}_{n}"`, `value = score`
- justification row → `step = "{stepid}.{base}_just_{n}"`, `value = justification`

`score` prefers the revoiced `phase_backfill.json` value, falling back to the worklist `target_score`;
`justification` comes from `phase_backfill.json` (revoiced), else `""`.

**The step-id / field mapping** (this is the fiddly part — it must match the collection form exactly):

*Field base per dim* (`overall`→`overall_rating`, `completeness`→`completeness_quality`, all others =
the dim name; justification field = base + `_just`):
```
overall→overall_rating  clinical_accuracy→clinical_accuracy  safety_triage→safety_triage
completeness→completeness_quality  communication_tone→communication_tone
instruction_following→instruction_following  interaction_efficiency→interaction_efficiency
multimodal_fidelity→multimodal_fidelity  personal_context→personal_context
ui_experience→ui_experience  worth_using_again→worth_using_again
```

*Step id + suffix* — depends on the task's **form type** (`meta[t]` / `taxonomy` → Form A/B/C):
- **Form C** — keyed by **provider identity**, fixed suffix:
  `chatgpt → (step-ResponseTextCollection-e5e516fcaeda, 1)` ·
  `claude → (…-d3fb717a6196, 2)` · `gemini → (…-b0eeaf40bd9a, 3)`
- **Form B** — keyed by **slot** (`n = provider_order.index(prov)+1`):
  `1 → step-TextCollection-970d11e30964` · `2 → …-1d5d1f26cd9c` · `3 → …-084a3c17e83d`

For Form C, `n` is the fixed suffix from the tuple; for Form B, `n` is the slot index. `provider_order`
comes from `meta[t]['provider_order']` (default `[chatgpt, claude, gemini]`).

---

## 3. `backfill_forms.csv` — corrected ratings, WIDE (`build_sheets.py`)

**Scope:** `category=='backfill'`, level L1. A reviewer-friendly wide form carrying only the three
actioned dims per provider (**overall / clinical / triage**).

**Columns** — base + per-provider (n=1,2,3):
```
base: form, review_level, form_type, task_id, main_action, provider_1..3,
      chatgpt/claude/gemini_session_link, original_persona, persona, persona_name,
      persona_description, ratings_qc_flag
per:  p{n}_generated_upload, p{n}_overall_rating, p{n}_overall_justification,
      p{n}_clinical_rating, p{n}_clinical_justification, p{n}_triage_rating, p{n}_triage_justification
```
- Each score = worklist `target_score` if that dim `needs_rewrite`, else the contributor original;
  justification = revoiced `phase_backfill` if rewritten (and present), else the original.
- `p{n}_generated_upload` = the provider's produced-artifacts JSON re-serialized, or `[]`.
- `persona` block filled only on a correction (see #4); `ratings_qc_flag = yes` when there's a ratings
  disagreement or gating violation. `main_action = backfill`.

---

## 4. `persona_updates.csv` — persona corrections (`build_persona_sheet.py`)

**Scope:** `category=='backfill'` tasks with a real persona mismatch (`fits_assigned_persona==false`).
Dedupes by task across any **carryover run dirs** passed as extra argv.

**Columns:** `task_id, original_persona, persona, persona_name, persona_description, needs_bot_attempt`.
- `persona`/`persona_name`/`persona_description` from the corrected persona via `persona_cols()`:
  `acute → acute_care / Acute Care / …`, `frontier → frontier_health / Frontier Health / …`,
  `lifestyle → lifestyle / Lifestyle / …`.
- `needs_bot_attempt = yes` if the task also has ≥1 dimension rewrite (so it needs a fresh bot attempt),
  else `no`.

---

## 5. `contributor_feedback.csv` — parity/structural only (`build_contributor_feedback.py`)

**Scope:** `category=='needs review'` **and needs-drivers ⊆ {parity, structural}** (a task with any
other NEEDS driver is excluded — it goes to `external_feedback.csv` instead).

**Logic:** feedback text = the cleaned reviewer-facing prose from `phase_external.json` — the `session`
+ `misc` bullets, **deliberately excluding the `rate` (ratings/justification) notes**. Fallback: the
raw parity detail, else `"Needs review for a parity/structural issue."`.

**Columns:** `task_id, contributor feedback`. Also writes `contributor_feedback_ids.json`, which
`build_sheets.py` reads to **exclude these tasks from `external_feedback.csv`** (no double-reporting).

---

## 6. `external_feedback.csv` — reviewer-facing, needs-review (`build_sheets.py`)

**Scope:** `category=='needs review'`, level L1, **minus** the `contributor_feedback_ids`.

**Columns:** `task_id, form_type, level, category, session_errors_external,
artifact_upload_errors_external, rate_justification_errors_external, misc_errors_external,
chatgpt/claude/gemini_session_link`.

The four `*_external` cells are the LLM-cleaned prose from `phase_external.json` (`session / artifact /
rate / misc`), `n/a` when empty. That prose is produced by `qa_active_external.js` from the
`external_input/<tid>.json` files, which `build_external_input.py` assembles from `eval_findings.csv`:
- **session_errors** ← PARITY (only if `FAIL`) · STRUCTURAL · UK IN SESSION
- **artifact_upload_errors** ← `artifact_errors` (wrong-PDF)
- **rating_errors** ← RATINGS DISAGREEMENT · JUSTIFICATION INCONSISTENCY · CITATION NEEDED · GATING · UK IN JUSTIFICATION
- **misc_errors** ← NO VALID STUMP · META LEAK · NOT HEALTHCARE · PERSONA MISMATCH

---

## 7. `ratings_disagreements.csv` — adjudication sheet (`build_disagreements.py`)

**Scope:** every task/provider/dim where the ratings eval set `disagree=true` (both bucket-cross and
within-bucket; a `bucket_cross` column marks which). Sorted bucket-cross first.

**Columns:** `task_id, level, form_type, provider, dimension, bucket_cross, cb_score, my_score,
clamped_target, contributor_justification, my_reason, rubric_basis, category, session_link`.
- `clamped_target` = the up-to-3/down-to-2 clamp (only for bucket-cross rows).
- `bucket_cross` = `YES (actioned)` vs `no (fyi/within-bucket)`.
- `rubric_basis` = the exact rubric anchor text for that dim at `my_score` (quoted from the rubric); for
  `overall` it appends the gating rule string.
