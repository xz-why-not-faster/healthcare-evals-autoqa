export const meta = {
  name: 'usecase-category',
  description: 'Classify each task into its persona×modality use-case category (non-agentic / artifact-generation only; NEVER an agentic type). Uses persona, modality, input-artifact names, and the 3 providers rubric justifications as signal.',
  phases: [{ title: 'Categorize' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const DIR = `${ROOT}/qa_pipeline_active/.catcls`   // per-task classifier inputs (written by the companion Python step)
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a && _a.ids) ? _a.ids : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args (array)')

const SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['task_id', 'category', 'confidence', 'reasoning', 'runner_up'],
  properties: {
    task_id: { type: 'string' },
    category: { type: 'string' },          // MUST be one of the allowed slugs
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    reasoning: { type: 'string' },         // 1-2 sentences citing the signal used
    runner_up: { type: 'string' },         // next best allowed slug, or ""
  },
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Classify ONE Healthcare Evals task into its single best USE-CASE CATEGORY. Read ${DIR}/${tid}.json — it has: persona, modality, artifacts (uploaded file names), allowed (an object of {slug: definition} — the ONLY categories you may choose from), and the ACTUAL TASK MATERIAL: prompt (opening user message), user_scenario, desired_end_state, trajectory_plan, and user_turns (the first several user messages of the real conversation).\n\n` +
      `Pick the ONE slug from "allowed" that best fits what the user was doing in this task. Rules:\n` +
      `- You may ONLY return a slug that is a key in "allowed". Never invent a slug and never return an agentic category (none are in "allowed" by design).\n` +
      `- Base the call on the ACTUAL TASK MATERIAL: what the user asks for in the prompt/user_turns, the desired_end_state, and the artifact names (e.g. a lab PDF => lab result; a discharge/instruction doc => care document; a scan/report to interpret => report/lab interpretation; a food photo => meal; raw genetic data => genetic). The desired_end_state and trajectory_plan usually state the core intent directly.\n` +
      `- Distinguish artifact-generation categories (the model BUILDS a reusable plan/tracker/log/dashboard) from plain non-agentic Q&A: if the rubrics/artifacts show the deliverable was a structured plan, tracker, or generated document the user keeps, prefer the artifact-generation slug; if it was explanation/interpretation/advice, prefer the interpretive slug.\n` +
      `- If two fit, pick the dominant intent of the session and name the other as runner_up.\n` +
      `- confidence: "high" if the task material clearly points to one slug; "medium" if the intent is somewhat mixed; "low" only if the material genuinely spans multiple categories or the allowed set has no good fit for what actually happened.\n\n` +
      `Return JSON: task_id="${tid}", category=<one allowed slug>, confidence, reasoning (1-2 sentences naming the concrete signal), runner_up=<another allowed slug or "">.`,
      { label: `cat:${tid}`, phase: 'Categorize', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
