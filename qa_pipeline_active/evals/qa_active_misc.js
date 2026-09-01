export const meta = {
  name: 'session-misc-errors',
  description: 'MISC session-level errors. (A) Task-level: is the task genuinely healthcare/clinical, or really insurance/admin/off-topic? (B) Per-turn user meta-instruction leaks a real user would not say: (1) asking the model to rate/score itself, (2) telling the model to use US guidance. Part B is extensible via CHECKS.',
  phases: [{ title: 'MiscErrors' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a && _a.ids) ? _a.ids : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args (array, or {ids:[...]})')

// The catalog of misc-error types. Each is a thing the USER says that a real user wouldn't —
// add new {type, desc} here and the prompt/schema pick it up automatically.
const CHECKS = [
  { type: 'rate_self', desc: 'The user explicitly asks the MODEL to rate, score, grade, or evaluate its OWN response/itself (e.g. "rate your answer 1-5", "how would you score yourself on accuracy", "give yourself a confidence score"). A real user does not ask the assistant to grade itself — this leaks the eval framing.' },
  { type: 'us_guidance', desc: 'The user explicitly tells the model to USE US / American guidance/guidelines/standards (e.g. "use US guidelines", "base this on US medical guidance", "assume US guidelines apply"). Steering the model to a guideline geography by fiat is a construction artifact, not something a real patient says.' },
]

const ISSUE = {
  type: 'object', additionalProperties: false,
  properties: {
    type: { enum: CHECKS.map((c) => c.type) },
    provider: { enum: ['chatgpt', 'claude', 'gemini'] },
    turn: { type: ['integer', 'null'] },   // 1-based user turn where it occurs
    quote: { type: 'string' },             // short verbatim snippet of the user's instruction
  },
  required: ['type', 'provider', 'turn', 'quote'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    task_id: { type: 'string' },
    healthcare_related: { type: 'boolean' },   // is this genuinely a health/clinical task at all?
    domain: { enum: ['clinical', 'fitness_wellness', 'mental_health', 'nutrition', 'insurance_admin', 'off_topic', 'other'] },
    domain_note: { type: 'string' },           // one line on the subject matter
    issues: { type: 'array', items: ISSUE },   // per-turn meta-instruction leaks; empty array if clean
  },
  required: ['task_id', 'healthcare_related', 'domain', 'domain_note', 'issues'],
}

const CATALOG = CHECKS.map((c) => `- ${c.type}: ${c.desc}`).join('\n')

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json. Under "providers", each of the three (chatgpt, claude, gemini) has transcript.turns, where every turn has "user" (the user's message) and "response" (the model). Scan ONLY the USER messages.\n\n` +
      `PART A — HEALTHCARE RELEVANCE (task-level): is this genuinely a HEALTH / CLINICAL task? healthcare_related=true for medical/clinical questions, symptoms, labs, medications, diagnoses, mental health, nutrition, or fitness/wellness pursued for a health goal. healthcare_related=false when the task is really insurance / benefits / billing / coverage selection, pure scheduling or admin, or an off-topic non-health subject. Set domain to the best label and domain_note to one sentence on the subject.\n\n` +
      `PART B — per-turn meta-instruction leaks: flag every MISC SESSION ERROR — an unnatural meta-instruction in the USER's message that a real person would not say. The types:\n${CATALOG}\n\n` +
      `Rules for Part B: only flag the USER's own words (never the model's response). Judge each provider's transcript independently (the same leak may appear in 1, 2, or all 3). Require an EXPLICIT instruction — do not flag a user who merely mentions being in the US, or who naturally asks a clinical question; it must actually direct the model to use US guidance, or actually ask the model to rate/grade itself. Quote the user verbatim (short snippet) and give the 1-based turn number.\n\n` +
      `Return JSON: task_id="${tid}"; healthcare_related; domain; domain_note; issues = an array of {type, provider, turn, quote}, one entry per occurrence (empty array [] if no leaks).`,
      { label: `misc:${tid}`, phase: 'MiscErrors', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
