export const meta = {
  name: 'external-rewrite',
  description: 'Rewrite the internal (auditor) error detail for each task into concise, plain-language, reviewer-facing bullets for the three external columns.',
  phases: [{ title: 'ExternalRewrite' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
// args = { run: "<run folder>", ids: [task_id, ...] }; each agent Reads <run>/external_input/<tid>.json.
let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) {} }
let RUN = (A && A.run) ? A.run : `${ROOT}/qa_pipeline_active/2026-08-20_0918`
if (!RUN.startsWith('/')) RUN = `${ROOT}/${RUN}`
const TASK_IDS = (A && A.ids) || []
if (!TASK_IDS.length) { log('no tasks to rewrite'); return [] }
log(`rewriting ${TASK_IDS.length} tasks`)

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    task_id: { type: 'string' },
    session: { type: 'string' },
    artifact: { type: 'string' },
    rate: { type: 'string' },
    misc: { type: 'string' },
  },
  required: ['task_id', 'session', 'artifact', 'rate', 'misc'],
}

const GUIDE =
  `You are writing feedback that a CONTRIBUTOR (not an auditor) will read to fix their Healthcare-Evals task. ` +
  `A task is 3 parallel AI conversations (ChatGPT, Claude, Gemini) that must be a valid comparison, each rated on clinical/safety rubrics.\n\n` +
  `Rewrite the auditor's internal notes into SHORT, PLAIN-LANGUAGE bullets. Rules:\n` +
  `- One "* " bullet per distinct issue. Each bullet is 1-2 complete sentences, roughly 30 words or fewer.\n` +
  `- Say WHAT is wrong (keep the single most useful specific — name the model, the file, the claim, the guideline) then WHAT TO DO. Drop turn-by-turn dumps, rubric jargon, internal codes (e.g. "type (a)", "2a", "BLOCKER", "gate"), and hedging.\n` +
  `- Third person. Refer to the audited model by name (ChatGPT/Claude/Gemini); never "I"/"we". Only compress the notes given — do NOT invent facts. You may keep a short quoted snippet if it earns its place.\n` +
  `- Plain fixes: broken link -> "Re-share it as a working public link, or re-generate the conversation."; parity/truncated/divergent -> re-run or re-generate so all three match; UK guidance -> re-generate that model with US guidance; missing generated file -> upload the file the model actually produced; missing citation -> add a specific source (a named guideline with year, a DOI/PMID, or a drug label); model safety-refusal -> regenerate that model's session.\n` +
  `- For rating bullets specifically: never just state a score is "too low/high" or "should be a 4". Always give the REASON grounded in the conversation — WHY the current score is wrong and WHY the corrected score fits, citing the concrete evidence (what the model actually did, the turn, the missed/handled item). E.g. not "ChatGPT completeness should be ~4 not 2" but "ChatGPT completeness should be ~4, not 2: it delivered the full audit and the only gap (potassium) was resolved at turn 11, and the 'no marketing warning' basis is contradicted at turn 7 where it does warn." Same for justification-inconsistency and citation bullets: name the specific claim and what the transcript shows / what source is needed.\n` +
  `- Misc bullets cover task-level issues that are NOT about a single rating: no valid stump / missed stump (after correcting the scores, explain plainly which model(s) do or don't actually stump and why), meta leaks (a user turn that breaks character — e.g. "I'm American, align to my country's guidance" or asking the model to rate itself; tell them to regenerate that turn without it), not-healthcare, realism problems, and persona mismatch (state the persona the task actually fits and why). Same grounded style: name the concrete evidence, don't just assert.\n` +
  `- Map 1:1: session_errors -> session, artifact_upload_errors -> artifact, rating_errors -> rate, misc_errors -> misc. If a source field is empty/(none), return "" for that column. Preserve the number of distinct issues (don't merge two models into one bullet).`

const results = (await parallel(TASK_IDS.map((tid) => async () => {
  try {
    return await agent(
      `${GUIDE}\n\n` +
      `Read the auditor notes for this task at ${RUN}/external_input/${tid}.json — a JSON object with fields ` +
      `{category, session_errors, artifact_upload_errors, rating_errors, misc_errors}. Rewrite each of the four error fields per the rules above. ` +
      `("category" is just the QA outcome label — ignore it; never output it.)\n\n` +
      `Return JSON: task_id="${tid}"; session = the rewrite of session_errors; artifact = the rewrite of artifact_upload_errors; ` +
      `rate = the rewrite of rating_errors; misc = the rewrite of misc_errors (NOT the category). Each is a newline-separated block of "* " bullets, or "" if that source field was empty/(none).`,
      { label: `ext:${tid}`, phase: 'ExternalRewrite', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
