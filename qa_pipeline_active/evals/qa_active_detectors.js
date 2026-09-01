export const meta = {
  name: 'transcript-detectors',
  description: 'ONE transcript read → four independent detector checks at once (uk-guidelines, misc/meta-leak+healthcare, persona-match, progressive-disclosure). Replaces the 4 separate evals to cut redundant full-transcript ingestion. Output splits back into the same 4 phase files.',
  phases: [{ title: 'Detectors' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a && _a.ids) ? _a.ids : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args')

const PERSONAS =
  `The taxonomy has EXACTLY three personas:\n` +
  `1. "Acute Care Analyzer" — a CURRENT medical issue: symptom triage/urgency, medication inquiry, understanding a diagnosis/term/test, self-care steps, decoding labs/discharge/after-visit docs, questions-for-the-doctor. Driver = a present health concern + appropriate level of care.\n` +
  `2. "Lifestyle Go-Getter" — GOAL-DRIVEN wellness: a fitness/diet/habit goal with plans, milestones, tracking, adherence/check-ins, meal/workout artifacts, tuning a plan against logs/wearables. Driver = pursuing a self-set lifestyle goal.\n` +
  `3. "Frontier Health User" — QUANTIFIED-SELF / LONGEVITY power user: biomarker/trend interpretation beyond reference ranges, protocol design (zones/supplements/fasting), hypothesis exploration on personal metrics, bespoke analytics over multi-source personal data (years of bloodwork, wearable exports, genetic data). Driver = optimization/analysis of a self-tracked system.`

const SCORES = { type: 'object', additionalProperties: false, properties: {
  opening_simplicity: { type: 'integer', minimum: 1, maximum: 5 }, conversational_disclosure: { type: 'integer', minimum: 1, maximum: 5 },
  few_files: { type: 'integer', minimum: 1, maximum: 5 }, healthcare_relevance: { type: 'integer', minimum: 1, maximum: 5 }, complexity_maintained: { type: 'integer', minimum: 1, maximum: 5 },
}, required: ['opening_simplicity','conversational_disclosure','few_files','healthcare_relevance','complexity_maintained'] }

const SCHEMA = {
  type: 'object', additionalProperties: true,
  properties: {
    task_id: { type: 'string' },
    uk: { type: 'object', additionalProperties: true, properties: {
      uk_in_session: { type: 'object', additionalProperties: true }, uk_guidelines_detail: { type: 'object', additionalProperties: true },
    }, required: ['uk_in_session','uk_guidelines_detail'] },
    misc: { type: 'object', additionalProperties: true, properties: {
      healthcare_related: { type: 'boolean' }, domain: { enum: ['clinical','fitness_wellness','mental_health','nutrition','insurance_admin','off_topic','other'] },
      domain_note: { type: 'string' }, issues: { type: 'array', items: { type: 'object', additionalProperties: true,
        properties: { type: { enum: ['rate_self','us_guidance'] }, provider: { enum: ['chatgpt','claude','gemini'] }, turn: { type: ['integer','null'] }, quote: { type: 'string' } },
        required: ['type','provider','turn','quote'] } },
    }, required: ['healthcare_related','domain','domain_note','issues'] },
    persona: { type: 'object', additionalProperties: true, properties: {
      original_persona: { type: 'string' }, fits_assigned_persona: { type: 'boolean' },
      suggested_persona: { type: ['string','null'], enum: ['Acute Care Analyzer','Lifestyle Go-Getter','Frontier Health User', null] }, detail: { type: 'string' },
    }, required: ['original_persona','fits_assigned_persona','suggested_persona','detail'] },
    progdisc: { type: 'object', additionalProperties: true, properties: {
      verdict: { enum: ['STRONG_EXEMPLAR','OK','NOT_EXEMPLAR'] }, scores: SCORES, file_turns: { type: 'integer' },
      opening_quote: { type: 'string' }, dump_turns: { type: 'string' }, one_line: { type: 'string' },
    }, required: ['verdict','scores','file_turns','opening_quote','dump_turns','one_line'] },
  },
  required: ['task_id','uk','misc','persona','progdisc'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json ONCE. Its "shared" block has contributor metadata (shared.persona, shared["user scenario"], shared["desired end state"], shared["trajectory plan"], shared.prompt). Under "providers", each of the three (chatgpt/claude/gemini) has transcript.turns — each turn has "user" and "response". From this single read, produce FOUR independent checks. Do not let one check bias another.\n\n` +

      `=== CHECK 1 — UK GUIDELINES (per provider, model side) ===\n` +
      `For EACH provider, does the MODEL invoke UK medical GUIDELINES or INSTITUTIONS in its responses, and where? COUNT: named UK guideline bodies + specific guidance (NICE incl. NG/CG/CKS, MHRA, BNF, GMC, CQC, SIGN, Royal Colleges, UK specialist societies) and UK health SERVICES (NHS 111/"111", 999, A&E, the NHS as a named institution/pathway). Non-UK (FDA, CDC, USPSTF, ACOG, AHA) do NOT count as UK. DO NOT COUNT "GP", "see your doctor", "call your clinic". Fill uk.uk_in_session = {chatgpt,claude,gemini}: true/false (false + note 'unavailable' if a transcript is empty/0-turns) and uk.uk_guidelines_detail = {chatgpt,claude,gemini}: the SPECIFIC UK guideline/institution + turn number(s), or "none".\n\n` +

      `=== CHECK 2 — MISC (healthcare relevance + per-turn meta leaks, USER side) ===\n` +
      `(A) misc.healthcare_related: is this genuinely a HEALTH/CLINICAL task (medical questions, symptoms, labs, meds, diagnoses, mental health, nutrition, fitness for a health goal)? false when it is really insurance/benefits/billing/coverage, pure scheduling/admin, or off-topic. Set misc.domain to the best label and misc.domain_note to one sentence.\n` +
      `(B) misc.issues: scan ONLY the USER messages for unnatural meta-instructions a real person would not say — type "rate_self" (user asks the MODEL to rate/score/grade ITSELF) or "us_guidance" (user explicitly tells the model to USE US/American guidance/guidelines/spelling). Require an EXPLICIT instruction (not merely mentioning being in the US). One entry per occurrence {type, provider, turn (1-based), quote (short verbatim)}; [] if none. Judge each provider independently.\n\n` +

      `=== CHECK 3 — PERSONA MATCH ===\n` +
      `${PERSONAS}\n` +
      `Question is NOT "which fits best" — it is: does this task GENUINELY NOT FIT the ASSIGNED persona (shared.persona) AT ALL? Personas overlap heavily on File-Upload tasks, so persona.fits_assigned_persona=TRUE whenever the assigned persona is a DEFENSIBLE reading of the user's driver. Set FALSE only when the assigned persona is clearly WRONG and the driver plainly belongs to another. Judge by the USER'S DRIVER, not surface features (uploading a lab does not make it Frontier — Acute Care also decodes labs). Fill persona.original_persona (exact shared.persona), persona.fits_assigned_persona, persona.suggested_persona (null if it fits, else the ONE it should be), persona.detail (2-4 sentences citing scenario/turns).\n\n` +

      `=== CHECK 4 — PROGRESSIVE DISCLOSURE (USER side; use whichever provider's transcript is most complete) ===\n` +
      `Gold pattern: OPEN with a simple natural worry, then mostly TALK — follow-up questions, reactions, small context in words — with MINIMAL attachments (ideally 0-1). Penalize hard: (1) FILE-PILING — a NEW document uploaded almost every turn (unnatural context stacking); (2) NOT HEALTHCARE — really insurance/billing/admin. Score each 1-5 (5 best): opening_simplicity, conversational_disclosure, few_files, healthcare_relevance, complexity_maintained. progdisc.verdict = STRONG_EXEMPLAR (simple opener, mostly conversational, few/no files, genuinely clinical, still substantive), OK (decent but flawed), NOT_EXEMPLAR (file-piling / not healthcare / trivial). Also progdisc.file_turns (count of user turns that introduce a NEW attached file), progdisc.opening_quote (verbatim snippet of the first user message), progdisc.dump_turns (turns that pile on files, or "none"), progdisc.one_line (one reviewer-facing sentence).\n\n` +

      `Return JSON: task_id="${tid}"; uk{uk_in_session, uk_guidelines_detail}; misc{healthcare_related, domain, domain_note, issues}; persona{original_persona, fits_assigned_persona, suggested_persona, detail}; progdisc{verdict, scores, file_turns, opening_quote, dump_turns, one_line}.`,
      { label: `detectors:${tid}`, phase: 'Detectors', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
