# Changes

Newest first. Format: `* [YYYY-MM-DD] short note`.

* [2026-09-01] sandbox-eval-sync skill: stores the live sandbox audit prompt and recommends surgical edits to keep it in sync with our chat-session evals (recommends only, never auto-applies) — first sync adds the input-parity/no-inferred-receipt rule to the sandbox parity section.

* [2026-09-01] Verify step (new): after categorize, re-run stump on no-stump tasks, LLM-recheck wrong_pdf flags, and re-adjudicate stumps against CB feedback — flips/clears then re-categorizes.
* [2026-09-01] Low-effort cleanup: rewrite phoned-in placeholders — critical dims full, multimodal/personal_context N/A→score 3 kept, other weak dims brief 1-sentence; anchor phrases left alone.
* [2026-09-01] Fixed backfill wide-form key bug (clinical/triage showed contributor's original → false gating violations); affected all prior deliveries.
* [2026-09-01] Contributor feedback: route wrong_pdf-only tasks to the contributor pool and include the PDF issue text (was showing bare "PASS").
* [2026-09-01] Melt now emits score-only N/A→3 dims (score 3, "N/A" kept).
* [2026-09-01] README rewritten as the single comprehensive reference (eval workflow, categorization, deliverables, Redash source).
