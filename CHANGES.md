# Changes

Newest first. Format: `* [YYYY-MM-DD] short note`.

* [2026-09-01] README: ordered the driver table by touch — reviewer drivers first, then attempter, then backfill.

* [2026-09-01] README: driver table Category column now shows the needs-review split per driver (→ reviewer vs → attempter).

* [2026-09-01] Needs-review routing: reviewer (high touch) = {no_valid_stump, uk_in_session, not_healthcare}; all other needs-review (parity/structural/wrong_pdf/meta_leak) go to the original attempter. A task falls to its highest-touch category (reviewer > attempter > backfill > no issues). Updated build_contributor_feedback.py + README (routing note, reordered deliverables table to the 5 that ship, moved secondary ones to a note).

* [2026-09-01] README: folded the red-flag/triage gate into a `†` footnote on the eval chart (referenced by the ratings & justif rows) instead of a standalone section.

* [2026-09-01] README clarity: removed the eval-workflow ASCII diagram, clarified that the per-task "case file" contains the full transcripts, and explained the legacy `phase*` filenames.

* [2026-09-01] README clarity: rewrote "The eval workflow" as a plain 3-stage narrative (ingest → battery → categorize) and moved the by-hand run.py command block into an Appendix.

* [2026-09-01] README: noted backfill_melt is currently shared directly with the FDE (no Compass workflow yet), and added a top "Work in progress" section (tracking returned L1 tasks, L10 eval workflows, cross-eval quality/contributor tracking).

* [2026-09-01] README: documented the post-eval Compass workflows (external→needs-review metadata, persona→L12 auto-send, contributor→send-back-to-attempter) and a "corrections after the first run" section for the verify passes.

* [2026-09-01] sandbox-eval-sync skill: stores the live sandbox audit prompt and recommends surgical edits to keep it in sync with our chat-session evals (recommends only, never auto-applies) — first sync adds the input-parity/no-inferred-receipt rule to the sandbox parity section.

* [2026-09-01] Verify step (new): after categorize, re-run stump on no-stump tasks, LLM-recheck wrong_pdf flags, and re-adjudicate stumps against CB feedback — flips/clears then re-categorizes.
* [2026-09-01] Low-effort cleanup: rewrite phoned-in placeholders — critical dims full, multimodal/personal_context N/A→score 3 kept, other weak dims brief 1-sentence; anchor phrases left alone.
* [2026-09-01] Fixed backfill wide-form key bug (clinical/triage showed contributor's original → false gating violations); affected all prior deliveries.
* [2026-09-01] Contributor feedback: route wrong_pdf-only tasks to the contributor pool and include the PDF issue text (was showing bare "PASS").
* [2026-09-01] Melt now emits score-only N/A→3 dims (score 3, "N/A" kept).
* [2026-09-01] README rewritten as the single comprehensive reference (eval workflow, categorization, deliverables, Redash source).
