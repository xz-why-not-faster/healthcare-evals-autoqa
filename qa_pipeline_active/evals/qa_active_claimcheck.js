export const meta = {
  name: 'justification-claimcheck',
  description: 'Per task: decompose each rating justification into its DISTINCT factual assertions about the conversation, and verify EACH against the actual transcript turns — flagging any assertion the transcript CONTRADICTS or does not support. Catches justifications that describe things the model did not do (the tethering/vitamin-C/"did not ask about meds" failure mode).',
  phases: [{ title: 'ClaimCheck' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
// {run, ids} where <run>/phase_backfill.json holds {tid:{providers:{prov:{overall|clinical|triage:{justification}}}}}
// OR {ids} to check the CONTRIBUTOR justifications straight from the case file.
const RUN = (_a && _a.run) ? _a.run : null
const JUST_FILE = RUN ? (RUN.startsWith('/') ? `${RUN}/phase_backfill.json` : `${ROOT}/${RUN}/phase_backfill.json`) : null
const taskIds = Array.isArray(_a) ? _a : (_a && _a.ids) ? _a.ids : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args (array, or {run, ids:[...]})')

const CLAIM = {
  type: 'object', additionalProperties: false,
  required: ['assertion', 'type', 'verdict', 'turn', 'evidence'],
  properties: {
    assertion: { type: 'string' },
    type: { type: 'string', enum: ['positive', 'negative', 'clinical_fact'] }, // negative = "model did NOT do X"; clinical_fact = external medical claim (not transcript-checkable here)
    verdict: { type: 'string', enum: ['SUPPORTED', 'CONTRADICTED', 'UNSUPPORTED', 'NOT_TRANSCRIPT_CHECKABLE'] },
    turn: { type: ['integer', 'null'] },
    evidence: { type: 'string' }, // the transcript quote that supports/contradicts, or ""
  },
}
const DIMOBJ = { type: 'object', additionalProperties: false, required: ['claims'],
  properties: { claims: { type: 'array', items: CLAIM } } }
const PROV = { type: 'object', additionalProperties: DIMOBJ }
const SCHEMA = { type: 'object', additionalProperties: true, required: ['task_id', 'providers', 'any_contradicted'],
  properties: { task_id: { type: 'string' }, providers: { type: 'object', additionalProperties: PROV }, any_contradicted: { type: 'boolean' } } }

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    const src = JUST_FILE
      ? `the rewritten justifications in ${JUST_FILE} under key "${tid}" (providers -> {overall|clinical|triage} -> justification)`
      : `each provider's contributor justifications inside ${WS}/task_${tid}.json (providers -> ratings -> {overall, clinical_accuracy, safety_triage}.justification)`
    return await agent(
      `You are FACT-CHECKING rating justifications against the actual conversation for one Healthcare Evals task. Read the FULL transcript for every provider in ${WS}/task_${tid}.json (providers.<p>.transcript.turns — each turn has the user message and the model response), then read the justifications to check: ${src}.\n\n` +
      `Check the overall, clinical_accuracy (a.k.a. "clinical") and safety_triage (a.k.a. "triage") justifications for each provider that has one.\n\n` +
      `METHOD — decompose, then verify each piece:\n` +
      `1. Break each justification into its DISTINCT FACTUAL ASSERTIONS ABOUT THE CONVERSATION — statements that can be checked against the turns. Examples: "the model asked for the medication name" (positive), "the model never asks which drug was prescribed" (negative), "at turn 11 it listed tethering", "it missed the saddle-anaesthesia red flag", "it recommended vitamin C". Also separate out any EXTERNAL CLINICAL FACT (e.g. "ibuprofen is contraindicated in CKD") — mark those type="clinical_fact" and verdict="NOT_TRANSCRIPT_CHECKABLE" (a different eval handles those; do not judge them here).\n` +
      `2. For EACH transcript-checkable assertion, SEARCH the actual turns and assign a verdict:\n` +
      `   • SUPPORTED — a specific turn confirms it. Give the turn number and a short verbatim quote.\n` +
      `   • CONTRADICTED — a specific turn shows the OPPOSITE of the assertion. Give the turn number and the quote. (THIS IS THE MOST IMPORTANT CATCH.)\n` +
      `   • UNSUPPORTED — you cannot find anything in the transcript that confirms it (and nothing that contradicts it either).\n\n` +
      `CRITICAL — NEGATIVE / OMISSION CLAIMS are where justifications most often lie. A claim of the form "the model did NOT do X / failed to ask about X / never mentions X / does not interpret X" is CONTRADICTED the moment you find ANY turn where the model DID do X. Before accepting a negative claim as SUPPORTED, you must scan the WHOLE transcript for a counter-example and quote it if found. (Real example this is built to catch: a justification says "the model does not ask which pain medication was given," but turns 4-5 show the model asking "tell me the name and dose"; or "the model does not interpret the tethered cord," but turn 11 shows it naming tethering — both are CONTRADICTED.)\n\n` +
      `Be literal and evidence-bound: judge only what the words assert, quote the exact turn, and do not give a claim the benefit of the doubt — if the transcript does not clearly bear it out, it is UNSUPPORTED or CONTRADICTED, not SUPPORTED.\n\n` +
      `Return JSON: task_id="${tid}"; providers = { <provider>: { <dim among overall/clinical/triage that has a justification>: { claims: [ { assertion:<the specific factual assertion, quoted or closely paraphrased>, type:<"positive"|"negative"|"clinical_fact">, verdict:<per above>, turn:<int or null>, evidence:<verbatim transcript quote proving the verdict, or ""> } ] } } }; any_contradicted = true if ANY claim in the task is CONTRADICTED. Include only providers/dims that actually have a justification to check.`,
      { label: `claimcheck:${tid}`, phase: 'ClaimCheck', schema: SCHEMA, effort: 'high' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
