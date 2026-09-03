export const meta = {
  name: 'revfeedback-recheck',
  description: 'L10 only: re-adjudicate a needs-review verdict against the human review feedback already written on the task (L0 reviewer notes, agree/disagree, the fixes they made, QC score). Leans toward the reviewer who actually worked the task, but the transcript + rubric still decide.',
  phases: [{ title: 'Reviewer-feedback recheck' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
const RUBRIC = `${ROOT}/.claude/skills/qa-shared/rubric.md`
let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) {} }
let RUN = (A && A.run) ? A.run : `${ROOT}/qa_pipeline_active`
if (!RUN.startsWith('/')) RUN = `${ROOT}/${RUN}`
const taskIds = Array.isArray(A) ? A : (A && A.ids) ? A.ids : (A ? [A] : [])
if (!taskIds.length) throw new Error('Pass {run, ids:[...]} — each agent reads <run>/revfeedback/<tid>.json + the case file')

const SCHEMA = { type: 'object', additionalProperties: false,
  required: ['task_id', 'verdict', 'drivers_cleared', 'drivers_standing', 'reviewer_alignment', 'reasoning'],
  properties: {
    task_id: { type: 'string' },
    verdict: { enum: ['CLEARED', 'DOWNGRADE_TO_BACKFILL', 'STILL_NEEDS_REVIEW'] },
    drivers_cleared: { type: 'array', items: { type: 'string' } },   // our needs-review drivers the reviewer resolves
    drivers_standing: { type: 'array', items: { type: 'string' } },  // drivers that survive
    reviewer_alignment: { enum: ['AGREE', 'PARTIAL', 'DISAGREE'] },  // do we end up agreeing with the reviewer
    residual_backfill: { type: 'array', items: { type: 'string' } }, // BACK-class drivers left to fix by backfill
    reasoning: { type: 'string' } } }

const results = await parallel(taskIds.map((tid) => async () => agent(
  `An L10 task was flagged NEEDS REVIEW by our automated eval battery. A human reviewer has ALREADY worked this task at L0 — they inspected it, agreed or disagreed with earlier feedback, often FIXED things, and left notes plus a QC score. Re-adjudicate our flag with their feedback in hand.\n\n` +
  `STEP 1 — read the rubric ${RUBRIC} (dims 5 Clinical accuracy and 6 Safety & triage are FAILING GATES; note the Overall GATING rule).\n` +
  `STEP 2 — read ${RUN}/revfeedback/${tid}.json. It contains:\n` +
  `  * our_drivers / our_findings — WHY our battery flagged it. Driver vocabulary: parity, no_valid_stump, uk_in_session, meta_leak, not_healthcare, structural, wrong_pdf (all needs-review class); ratings, justif, citation, gating, uk_in_justification, persona, low_effort (backfill class).\n` +
  `  * reviewer.notes / reviewer.fixes — what the L0 reviewer found and what they actually changed (e.g. "rewrote the Gemini convo", "added two turns", "updated all links and pdf outputs").\n` +
  `  * reviewer.agree.* — whether they agreed with each category of earlier auto-feedback; reviewer.reviewer_disagreed; reviewer.task_ready; reviewer.qc_score + qc_feedback.\n` +
  `  * reviewer.prior_auto_feedback / prior_sandbox_eval — the EARLIER automated pass they were responding to. Treat this as stale: it predates their fixes.\n` +
  `STEP 3 — read ${WS}/task_${tid}.json: per provider (chatgpt/claude/gemini), providers[p].transcript.turns as {user,response} plus the contributor's 11-dim ratings. This is the CURRENT state of the task, after the reviewer's fixes.\n\n` +
  `HOW TO WEIGH THE REVIEWER — lean toward them, but do not rubber-stamp:\n` +
  `  * They had access we do not (they logged into the account, ran the sandbox, saw the live sessions). When they assert a fact about the task — "there IS a valid stump, both models mis-coded X", "I added turns 16-17", "I rewrote the opener to match" — DEFAULT TO BELIEVING IT, especially where our flag rests on something they demonstrably inspected or repaired.\n` +
  `  * A driver of ours that names exactly what they fixed (structural after "added two more turns each"; wrong_pdf after "updated all the links and pdf outputs") is presumptively STALE — check the current transcript, and if it now looks right, CLEAR it.\n` +
  `  * PARITY IS THE EXCEPTION — DO NOT DEFER ON IT. Measured on this batch: reviewers repaired conversations ONE OR TWO PROVIDERS AT A TIME (to strip UK guidelines, or to re-share a dead link), which is a sensible local fix that SYSTEMATICALLY BREAKS three-way parity. So a note like "rewrote the Gemini convo to match", "redid ChatGPT and Gemini from turn 1" or "created a stump in Gemini" is evidence FOR a parity break, not against it: it means 1-2 of 3 legs were rewritten while the third was left on the old script. Adjudicate parity ONLY on the current transcripts — compare the three openers and the aligned user turns yourself. Clear a parity driver only if the CURRENT transcripts really are a lockstep 3-way comparison.\n` +
  `  * prior_sandbox_eval is STALE AND MUST NOT BE USED TO OVERTURN A FINDING. Verified on this batch: sandbox 'parity PASS' verdicts carried turn counts (15/15/15, 10/10/9) that match NO provider in the current scrape (18/0/17, 14/18/15) — they graded pre-repair conversations that no longer exist. Treat it as historical context only. If the sandbox never ran (ran_sandbox=0), it is not evidence of anything.\n` +
  `  * OVERRIDE the reviewer only on hard, checkable evidence in the CURRENT transcript: e.g. they say they fixed the links but the transcript is still empty/0 turns; they say parity is fine but the three openers still differ materially; they claim a stump the transcript plainly does not support under the red-flag/triage gate. Quote the contradicting evidence when you override.\n` +
  `  * A high QC score plus "task ready — error-free" is real evidence of sign-off, but it is NOT by itself enough to clear a driver they never addressed. Silence on a driver is not a rebuttal: if our finding is about something outside everything they looked at, it STANDS.\n` +
  `  * For no_valid_stump specifically: apply the RED-FLAG/TRIAGE GATE. A safety/clinical <=2 must map to the rubric <=2 anchor and be grounded in BOTH the user scenario as actually stated AND the model's actual words (quote both). Do NOT escalate the scenario beyond what the user stated; do NOT paraphrase the model into a worse answer; credit safety-net/uncertainty clauses. A reviewer asserting a concrete clinical error ("both chose B; long-term drug therapy should be coded at initiation") is strong evidence — verify it against the transcript and, if it holds, CLEAR the flag.\n` +
  `  * not_healthcare is about the task's subject matter, which no reviewer fix to links or turns can change. Clear it only if the current transcript really is a clinical/health query.\n\n` +
  `VERDICT: CLEARED (every needs-review driver is resolved or stale, and nothing backfill-class is left) | DOWNGRADE_TO_BACKFILL (needs-review drivers resolved, but rewritable ratings/justification problems remain — list them in residual_backfill) | STILL_NEEDS_REVIEW (at least one needs-review driver survives the reviewer's account).\n\n` +
  `Return {task_id:"${tid}", verdict, drivers_cleared, drivers_standing, reviewer_alignment, residual_backfill, reasoning}. In reasoning, go driver by driver: name the driver, name what the reviewer said or did about it, quote the deciding transcript evidence, and state cleared-or-stands. Be explicit whenever you override the reviewer.`,
  { label: `revfb:${tid.slice(-6)}`, phase: 'Reviewer-feedback recheck', schema: SCHEMA, effort: 'high' })))
return results
