export const meta = {
  name: 'progressive-disclosure',
  description: 'Per task: does the OPENING prompt front-load a ton of context, or start simple and disclose across turns (as real users do)? Tracking only.',
  phases: [{ title: 'ProgressiveDisclosure' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args')

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    task_id: { type: 'string' },
    front_loaded: { type: 'boolean' },
    severity: { enum: ['heavy', 'moderate', 'none'] },
    detail: { type: 'string' },
  },
  required: ['task_id', 'front_loaded', 'severity', 'detail'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json — shared.prompt is the OPENING user prompt (identical across the 3 providers), and each provider has the full transcript turns.\n\n` +
      `We want conversations that mirror how real users behave: START SIMPLE and disclose context PROGRESSIVELY across turns, rather than front-loading a ton of context into the very first prompt. Example of the GOOD pattern: a user opens with "running has been harder recently even though I'm training regularly", THEN over later turns attaches training/food logs, shares bloodwork, and mentions symptoms — instead of dumping all of that (logs + shortness of breath + palpitations + lightheadedness + normal hemoglobin/ferritin) into turn 1.\n\n` +
      `Judge THIS task's opening prompt (and how the trajectory unfolds): does the FIRST prompt front-load a lot of context at once — multiple symptoms, lab values/bloodwork, full history, several constraints, or several attachments dumped together — instead of leaving that to emerge across turns?\n\n` +
      `Return JSON: task_id="${tid}"; front_loaded = true if the opening prompt packs in substantial context that a real user would more naturally reveal over multiple turns, else false; severity = "heavy" (opening dumps most of the scenario's facts/attachments), "moderate" (opening is a bit overloaded but leaves room), or "none" (already a clean, simple opener); detail = 1-2 sentences — what is front-loaded, and (if front_loaded) how it could open more simply with the rest disclosed across turns.`,
      { label: `progdisc:${tid}`, phase: 'ProgressiveDisclosure', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
