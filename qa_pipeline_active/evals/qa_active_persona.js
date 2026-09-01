export const meta = {
  name: 'persona-match',
  description: 'Per task: contributor-declared persona vs. an independent evaluated persona, and whether they match.',
  phases: [{ title: 'Persona' }],
}

const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args')

const PERSONAS = `The taxonomy has EXACTLY three personas:\n` +
  `1. "Acute Care Analyzer" — a CURRENT medical issue: symptom triage/urgency, medication inquiry, understanding a diagnosis/term/test, self-care steps, decoding labs/discharge/after-visit docs, questions-for-the-doctor. The driver is a present health concern and appropriate level of care.\n` +
  `2. "Lifestyle Go-Getter" — GOAL-DRIVEN wellness: a fitness/diet/habit goal with plans, milestones, tracking, adherence/check-ins, on-plan decisions, meal/workout artifacts, tuning a plan against logs/wearables. The driver is pursuing a self-set lifestyle goal.\n` +
  `3. "Frontier Health User" — QUANTIFIED-SELF / LONGEVITY power user: biomarker/trend interpretation beyond reference ranges, protocol design (zones/supplements/fasting), hypothesis exploration on personal metrics, deep research on emerging health/longevity science, bespoke analytics/dashboards over multi-source personal data (years of bloodwork, wearable exports, genetic data). The driver is optimization/analysis of a self-tracked system.`

const SCHEMA = {
  type: 'object', additionalProperties: true,
  properties: {
    task_id: { type: 'string' },
    original_persona: { type: 'string' },
    fits_assigned_persona: { type: 'boolean' },
    suggested_persona: { type: ['string', 'null'], enum: ['Acute Care Analyzer', 'Lifestyle Go-Getter', 'Frontier Health User', null] },
    detail: { type: 'string' },
  },
  required: ['task_id', 'original_persona', 'fits_assigned_persona', 'suggested_persona', 'detail'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json. Its "shared" block has the contributor-DECLARED metadata: shared.persona (the ASSIGNED persona), shared["task category"], shared["user scenario"], shared["desired end state"], shared["trajectory plan"], and shared.prompt. Each provider also has the full transcript turns.\n\n` +
      `${PERSONAS}\n\n` +
      `Your question is NOT "which persona fits best" — it is: does this task GENUINELY NOT FIT the ASSIGNED persona (shared.persona) AT ALL? Personas overlap heavily on File-Upload tasks, so set fits_assigned_persona=TRUE whenever the assigned persona is a DEFENSIBLE reading of the user's driver — even if another persona could also fit. Only set fits_assigned_persona=FALSE when the assigned persona is clearly WRONG: the user's actual driver plainly belongs to a different persona and the assigned one cannot be reasonably justified from the scenario/turns.\n\n` +
      `Judge by the USER'S DRIVER, not surface features: uploading a lab/PDF/genetic panel does not by itself make it Frontier (Acute Care Analyzer also decodes labs/discharge docs). A present worry needing care = Acute; pursuing a self-set fitness/diet/habit goal = Lifestyle; optimizing/analyzing a self-tracked system or longevity science = Frontier.\n\n` +
      `Return JSON: task_id="${tid}"; original_persona = the exact shared.persona string; fits_assigned_persona = true/false per the standard above; suggested_persona = null if it fits, otherwise the ONE persona it clearly should be (exact string); detail = 2-4 sentences citing the scenario/turns — if it fits, note the reading that justifies the assigned persona (and any tension); if it does NOT fit, explain why the assigned persona is untenable and what it clearly is instead.`,
      { label: `persona:${tid}`, phase: 'Persona', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) {
    log(`task ${tid} failed: ${e}`)
    return null
  }
}))).filter(Boolean)

return results
