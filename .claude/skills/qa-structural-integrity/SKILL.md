---
name: qa-structural-integrity
description: Priority-1 QA check for Healthcare Evals tasks. Audits structural soundness of a task's 3-provider submission — links work, transcripts look right/complete, opening prompt and uploads match across all 3, ≥15 turns each, and the contributor's generated files were uploaded and look right. Use when auditing a task's structural integrity from its case-file JSON.
---

# QA · Structural Integrity (Priority 1)

You audit ONE task (3 provider conversations: chatgpt/claude/gemini) for structural
soundness. This is the highest-priority gate: a task that fails here is invalid
regardless of content quality. It is **not purely deterministic** — you must also
judge whether transcripts and uploaded files actually *look right*.

Read `.claude/skills/qa-shared/rubric.md` (§ Structural gates) for the exact rules.

## Input
A case-file JSON at `qa_pipeline/workspace/task_<id>.json` containing, per provider:
the transcript (turns: user/response), all links with HTTP status, downloaded
artifacts (path/ctype/bytes), the shared prompt, and contributor ratings.

## The hard GATES are precomputed deterministically
The pipeline already computed the pass/fail gates in `case["gates"]` (min_length,
shared_prompt, same_uploads) and the onboarding-scaffolding normalization per provider.
**Read `case["gates"]` and report those results verbatim — do NOT recompute them.** Your job
is the JUDGMENT that code can't do. Still cross-check the deterministic result against the
transcript if something looks off, and flag any disagreement.

## Checks to perform

### 1. Read the precomputed gates
Report `case["gates"].min_length` (turns per provider, need ≥15), `.shared_prompt`
(identical across providers + matches CSV), `.same_uploads` (identical sha1 sets), and
`.onboarding_normalization` (which scaffolding turns were stripped). These are the GATE verdicts.

### 4. Transcript looks right (JUDGMENT)
For each transcript: is it coherent and complete, or truncated/garbled/cut mid-turn?
Do responses actually answer the user turns? Does the turn count plausibly match a
15–25 turn task? Flag "not public"/empty notes, missing responses, or extraction
artifacts. A transcript that ends mid-thought or has many empty responses is a defect.

### 5. Same uploads across the 3 — JUDGMENT layer on top of the gate
The `same_uploads` gate (sha1 equality of starting uploads) is precomputed. Add the judgment
code can't do: check the transcript for **later** upload points and whether the same files
appear across providers at matching points, and whether a provider's turns reference a file it
never actually received (a parity break even if the opening sha1s match). Flag these.

### 6. Links work — CORE JOB: flag EVERY broken link
**Prefer the LIVE status.** If `transcript.live_status` is present (from link_check.py, a fresh
re-load), use it as authoritative for the session link — a share can be DELETED/NOT_PUBLIC/empty
*after* ingest even though its recorded HTTP status was 200 (e.g. a deleted ChatGPT share still
returns 200). Any live_status other than WORKING is a broken deliverable. The recorded HTTP status
is only an ingest-time snapshot; do not rely on it alone.

Flagging broken links is a primary purpose of this audit — be exhaustive and explicit. For every
recorded link across all providers (task_link, artifact_folder, artifacts_start/throughout,
session_link, session_pdf, session_artifacts, screenshots): 200/206 = ok; list ANY that are dead
(404/5xx/errors), report each with provider + label + status. Special cases to always call out:
- **session link "not public"** → dead/unshared share link (a broken deliverable).
- **a Gemini session link that is `gemini.google.com/app/...`** rather than `share.gemini.google/...`
  → a private app URL, not a public share (broken as a submission).
- **session_pdf that references a different conversation** than the session_link → mismatch.
Treat `auth-required` dashboard.scale.com task links and Google Drive folders as "gated /
unverifiable, not broken." Confirm each session link yielded a real transcript (turns>0).

### 7. Generated files uploaded and look right (JUDGMENT)
The `session_artifacts` are the files the model generated during the session and the
contributor was required to upload. Verify they exist (downloaded, non-zero, right
content-type). Then open/inspect them (PDF/CSV/image) and judge whether they look
right: do they match what the conversation says was produced? Are they complete
(not blank, not a broken export with missing sections)? A missing or corrupt
generated-file upload is a structural defect. Also check `session_pdf` exists and
looks like a complete conversation export.

## Output (structured)
Return JSON:
```
{
  "task_id": "...",
  "gates": {
    "min_length": {"pass": bool, "turns": {"chatgpt":N,"claude":N,"gemini":N}, "detail": "..."},
    "shared_prompt": {"pass": bool, "detail": "..."},
    "same_uploads": {"pass": bool, "detail": "..."},
    "links_work": {"pass": bool, "detail": "..."},
    "transcript_present": {"pass": bool, "detail": "..."}
  },
  "judgments": {
    "transcript_looks_right": {"ok": bool, "detail": "..."},
    "generated_files_uploaded_and_ok": {"ok": bool, "detail": "..."}
  },
  "onboarding_normalization": "which turns were stripped, per provider",
  "issues": ["one concise line per real issue, most severe first, with provider + turn/link cited"],
  "verdict": "PASS" | "FAIL",
  "severity": "blocker" | "major" | "minor" | "none"
}
```
`verdict` = FAIL if any GATE fails. Keep `issues` specific and evidence-cited; these
lines feed the task's "issues found" CSV column.
