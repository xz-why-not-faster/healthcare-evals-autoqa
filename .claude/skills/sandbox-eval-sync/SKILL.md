---
name: sandbox-eval-sync
description: Keep the in-task SANDBOX audit eval in sync with our chat-session AutoQA evals. Use whenever a chat-session eval (qa_active_*.js — especially parity, ratings, justif, stump, detectors) is changed, or when the user asks how the sandbox eval should be updated, or when our eval and the sandbox disagree on a batch. RECOMMEND surgical edits only — never edit the sandbox prompt or apply changes autonomously.
---

# Sandbox-eval sync

The **sandbox** is the in-task automated audit the contributor sees while building a task (its prompt
is in [`sandbox_eval_prompt.md`](sandbox_eval_prompt.md); its output lands in the V19 `eval transcripts`
column). Our **chat-session AutoQA** (`qa_pipeline_active/evals/qa_active_*.js`) is the downstream
review. When we improve a chat-session eval, the sandbox drifts out of sync — contributors then get a
green light the downstream review later fails (e.g. "sandbox parity PASS" on a task we FAIL).

This skill produces **surgical, copy-pasteable edit recommendations** to bring the sandbox prompt back
in line. It does **not** change anything.

## Hard rules
- **NEVER** edit `sandbox_eval_prompt.md`, the live sandbox, or apply any change. Only recommend.
  `sandbox_eval_prompt.md` is a read-only mirror of the *current live* sandbox — keep it in sync with
  the real sandbox prompt, never with our recommendations.
- **Surgical only:** propose the smallest possible insertion/replacement into a specific sandbox
  section — quote the exact current sandbox line and the exact suggested new line. No rewrites of
  whole sections unless the user explicitly asks.
- **Output recommendations live** in the reply — do not persist them to a file.

## When to invoke
- After editing any `qa_active_*.js` (or its rules), to check whether the sandbox needs the same change.
- When the user reports a systematic sandbox-vs-review disagreement on a run (e.g. "sandbox parity passes").
- On request ("how should the sandbox eval be updated?").

## Eval → sandbox-section map
| Chat-session eval | Sandbox section it maps to |
|---|---|
| `qa_active_parity.js` | Section 1 · Conversation Parity |
| `qa_active_stump.js` / `valid_model_stump` in `qa_active_justif.js` | Section 2 · Model Stump |
| `qa_active_ratings.js`, `qa_active_justif.js`, `qa_active_evidence.js` | (no sandbox equivalent — sandbox stops at stump; note as "review-only") |
| `qa_active_detectors.js` → progdisc / voice | Sections 3 · Simplicity, 4 · Patient Speak |
| `qa_active_detectors.js` → uk | Section 6 · Guideline Steering |
| structural / turn-count | Sections 0 · Transcripts, 5 · Turn Count |
| `pdf_link_check.py` + `qa_active_pdfrecheck.js` | Section 1 · Correct upload (PDF↔link match) |

## Procedure
1. Read the changed eval's relevant rule(s) and the mapped sandbox section in `sandbox_eval_prompt.md`.
2. Diff the *intent*: what does our eval now flag that the sandbox section does not (or flags weaker)?
3. Write a surgical recommendation: **section**, the **exact current sandbox text** to change, the
   **exact suggested text**, a one-line **why**, and the **triggering eval change**.
4. Distinguish **prompt gaps** (the sandbox has the same data but reasons differently → fixable by a
   prompt edit) from **data/tooling gaps** (the sandbox loaded a transcript we couldn't, or vice
   versa → NOT a prompt fix; flag separately, do not recommend a prompt change for these).
5. Present the recommendation to the user in the reply. Make no edits to any file.
