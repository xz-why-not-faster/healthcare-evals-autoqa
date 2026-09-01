---
name: qa-intent-parity
description: Priority-1 HARD GATE for Healthcare Evals tasks. Verifies the three model conversations are a valid parallel comparison — same intent/scenario, the correct conversation uploaded for each provider, the same key inputs received at comparable points, and comparable trajectories toward the same desired end state. Fails the task on a parity break.
---

# QA · Intent & Conversation Parity (HARD GATE — blocker)

The whole point of a task is a 3-way comparison of the SAME scenario across ChatGPT/Claude/Gemini.
If the three conversations aren't genuinely parallel — different intent, a wrong conversation
uploaded, or one model missing a key input the others got — the comparison is invalid. This is a
**blocker gate**: a parity break fails the task regardless of content quality.

This CANNOT be judged from metadata alone. The tracker's upload columns are often copy-pasted across
the three rows, and only Gemini transcripts annotate `[attached: …]`. You MUST read the actual
conversation CONTENT of each provider and reason about what each one received and pursued.

Read `.claude/skills/qa-shared/rubric.md`. Input: the case-file JSON — the shared scenario,
`trajectory plan`, `desired end state`, all 3 transcripts, and `case["gates"]` (which includes
`throughout_parity` and `same_uploads` as hints only).

## Checks (read every transcript in full)

### 1. Same intent / scenario
Summarize each provider's actual intent and trajectory from its transcript. Do all three pursue the
SAME underlying scenario and the SAME desired end state (per `desired end state` / `trajectory plan`)?
Flag if one conversation is about a materially different thing, or drifts to a different goal.

### 2. Correct conversation uploaded (per provider)
Confirm each provider's transcript is the RIGHT conversation for this task and this provider:
- The transcript's persona/scenario matches the task (not another task's conversation, not a
  different topic).
- The `session_pdf` corresponds to the same conversation as the `session_link` — flag if the PDF
  is a different conversation / references a different URL / shows only refusals (as in a mis-upload).
- The provider labeled (e.g. "gemini") is actually that model's conversation.

### 2a. Opening-prompt parity (this IS a parity issue, not only a structural gate)
"Not all models were asked the same opening question" is a PARITY break. Compare the three providers'
FIRST user turn. Strip **ONLY** literal `[attached: …]` upload annotations before comparing —
nothing else. Then, if one provider's opening contains **any extra or different text** the others
lack, that is an opening-prompt parity break — FLAG it (major). This includes, and you must NOT
excuse as a harmless "annotation artifact":
- a leaked contributor/meta note prepended or appended to the prompt (e.g. "No justification as per
  guideline.", a pasted rating/justification fragment);
- a meta-instruction one model got and the others didn't (e.g. "disregard any memory or information
  from other chats", "use US guidance", "rate yourself") — flag it here AND note it as a meta leak;
- any reworded / added / removed sentence in one provider's opening.
The ONLY differences that are NOT a break: pure whitespace/punctuation/casing, and the stripped
`[attached: …]` tags themselves. Do NOT rationalize extra text as a scraping artifact — if it is in
the transcript's first user turn, treat it as text that provider received. NOTE:
all-three-identical-but-differ-from-CSV is NOT a parity break (trivial edit); a genuinely different
opening across providers IS.

### 2b. Turn-by-turn user-prompt alignment (do this carefully)
Align the USER turns across the three conversations by position and compare them. Follow-up
prompts need not be identical (natural responses differ), but FLAG deviations that "didn't have to
be there" and hurt comparability:
- a needless wording change injected into some models but not others (e.g. "what's interesting is…"
  prepended for 2 models, plain for the 3rd);
- an extra explicit ask given to some models but omitted for another (e.g. "Should I take it?"
  present for 2, missing for 1);
- an **offset / duplicated / fragment** user turn in one model (e.g. a truncated "oh no...spr" turn
  that shifts every later turn by one) — this means the models were not driven in lockstep.
Report each as a minor/major parity deviation with the turn number and the differing text.

### 2c. Attachment TIMING across models
Check WHEN each uploaded file was introduced in each conversation, not just whether the same files
exist. NOTE a scraping limitation: only **Gemini** transcripts annotate `[attached: …]` on the user
turn; **ChatGPT/Claude do not expose upload info**, so infer their attachment timing from the
model's RESPONSE first referencing the file. Flag if a file that others attached at the opening is
**missing from one model's first prompt and only added later** (e.g. a lab file forgotten in the
opening prompt for one model, attached a few turns in). Note whether it disrupted the conversation.

### 3. Same key inputs received at comparable points (CONTENT-BASED)
Determine, from the conversation content, which key inputs each conversation actually received and
used (files, data, images) — NOT from the tracker columns. The tell is whether the model analyzes
that input. Example: if ChatGPT and Gemini both do a cost optimization from a price CSV but Claude
never performs any cost analysis, Claude never effectively received the cost CSV — a parity break,
even though the tracker's `artifacts_throughout` is identical across rows. Flag any input one or two
providers used that another never did.

### 4. Missing mid-conversation artifacts
If the task design implies mid-conversation uploads (see `trajectory plan`), flag any provider whose
conversation introduces none while others do. Use `gates.throughout_parity.providers_missing_all`
and `gates.same_uploads` as hints, but confirm against the transcript.

### 5. Comparable trajectories / end state reached
Are the three parallel enough to be a valid comparison? Flag divergences that break comparability or
leave the desired end state unmet for a provider (e.g. one conversation ends before the planned
deliverable while others complete it).

## Verdict
- `FAIL` (blocker) if ANY of: intents materially diverge; a wrong/mismatched conversation or PDF was
  uploaded; a provider is missing a key input the others received; or a provider never pursues the
  shared desired end state so the 3-way comparison is invalid.
- `PASS` if the three are a genuine parallel comparison (natural follow-up differences are fine).

## Output (structured)
```
{
  "task_id": "...",
  "per_provider_intent": {"chatgpt":"one-line actual intent/trajectory", "claude":"...", "gemini":"..."},
  "same_intent": {"ok": bool, "detail": "..."},
  "correct_conversation_uploaded": {"ok": bool, "detail": "which provider is wrong/mismatched, if any"},
  "input_parity": {"ok": bool, "detail": "which provider missed which key input, cite the content tell"},
  "end_state_parity": {"ok": bool, "detail": "..."},
  "verdict": "PASS" | "FAIL",
  "severity": "blocker" | "major" | "minor" | "none",
  "issues": ["concise, evidence-cited lines — lead with the parity break; cite the provider + turn/content tell"]
}
```
These `issues` feed the task's "issues found" column; parity breaks are among the most important findings.
