---
name: qa-conversation-quality
description: Priority-2 QA check for Healthcare Evals tasks. Judges the quality of the conversation design across a task's 3 conversations — simple-premise/complex-ask, persona embodiment, trajectory toward the desired end state, and internal consistency with the uploaded artifacts. Use after structural integrity passes.
---

# QA · Conversation Quality & Task Design (Priority 2)

You judge whether the CONVERSATION and TASK DESIGN are good — separate from how the
models scored. Read `.claude/skills/qa-shared/rubric.md` (§ Task-design quality and
§ Model stump) for anchors. Input: the case-file JSON (shared scenario + trajectory +
desired end state, and all 3 transcripts).

## What to evaluate

### A. Simple premise, complex journey
The spec's core bar: an ordinary opening ask that develops into a clinically complex,
interconnected, multi-turn journey — NOT an exotic topic and NOT everything front-loaded.
- Does the opening prompt start ordinary/ambiguous, letting the model uncover the goal?
- Does complexity build over turns (progressive symptoms/results/constraints, passage of
  time, multi-source synthesis) rather than one-shot Q&A?
- Rate the 4 advisory task-design dimensions 1–5 (opening-prompt ambiguity, long-horizon
  complexity, personalization environment, everyday-topic framing) with a one-line reason each.

### B. Persona embodiment
Every task maps to a persona (Acute Care Analyzer / Lifestyle Go-Getter / Frontier Health
User) and a written user scenario. Judge whether the USER side of the conversation
consistently embodies that persona and scenario:
- Do the user's messages match the persona's intent/voice/domain (e.g. Lifestyle Go-Getter =
  coaching/planning for lifestyle goals)?
- Are the persona's stated facts (age, history, meds, constraints from `user scenario`) used
  consistently, or contradicted/forgotten mid-conversation?
- Does the conversation stay in the assigned modality (e.g. File Upload)?
Flag breaks: out-of-character asks, persona facts that drift, wrong modality.

### C. Trajectory → desired end state
Compare the actual conversation to `trajectory plan` and `desired end state`.
- Did the conversation pursue and (attempt to) reach the intended end goal / deliverable?
- Are the planned progressive reveals and required model actions (parsing, analysis, code,
  artifact generation, scheduling) actually present?
- Note material divergences (fine if a better trajectory emerged — flag only if it undermines
  the task's intent or the end state was never pursued).

### D. Internal consistency with artifacts
The spec demands everything stay internally consistent. Check the conversation against the
uploaded artifact(s): do the dates, values, medications, and facts the user states match the
file they uploaded? Flag contradictions (e.g. user says "5 supplements" but the organiser
shows 8; a date in the chat conflicts with the document).

### E. Conversation continuity (user self-consistency across turns)
Scan the USER's own turns for self-contradictions across the conversation, and whether the model
surfaces them on-record. Example: the user says he is already home checking his BP, then a turn
later asks "how can I get home?" — an on-record continuity blunder the model called out in the
shareable session. Flag: (a) user facts that contradict earlier turns (location, timing, vitals,
what was taken and when), and (b) whether the model noticed/handled or silently went along.
These break realism and the "keep everything internally consistent" requirement.

## Output (structured)
```
{
  "task_id": "...",
  "task_design_scores": {"opening_ambiguity":N, "long_horizon_complexity":N,
                          "personalization_environment":N, "everyday_topic_framing":N},
  "premise_complexity": {"ok": bool, "detail": "..."},
  "persona_embodiment": {"ok": bool, "persona": "...", "detail": "..."},
  "trajectory_end_state": {"ok": bool, "detail": "..."},
  "artifact_consistency": {"ok": bool, "detail": "..."},
  "issues": ["concise, evidence-cited lines, most severe first"],
  "severity": "major" | "minor" | "none"
}
```
Cite specific turns/artifacts. These `issues` feed the task's "issues found" column.
