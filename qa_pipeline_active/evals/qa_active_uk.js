export const meta = {
  name: 'uk-guidelines-eval',
  description: 'Per-provider: is UK (medical guidelines / institutions) present in the session, which ones, and where.',
  phases: [{ title: 'UK-guidelines' }],
}

const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args')

const SCHEMA = {
  type: 'object', additionalProperties: true,
  properties: {
    task_id: { type: 'string' },
    uk_in_session: { type: 'object', additionalProperties: true },        // {chatgpt,claude,gemini}: bool
    uk_guidelines_detail: { type: 'object', additionalProperties: true }, // {chatgpt,claude,gemini}: names + WHERE
  },
  required: ['task_id', 'uk_in_session', 'uk_guidelines_detail'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json — per provider (chatgpt/claude/gemini) it has the full transcript turns (user + response).\n\n` +
      `For EACH provider, determine whether the MODEL invokes UK medical GUIDELINES or medical INSTITUTIONS in its responses, and WHERE.\n\n` +
      `COUNT (these qualify):\n` +
      `• Named clinical-guideline bodies + their specific guidance: NICE (incl. specific refs like NG158 / CG168 / CKS / quality standards), MHRA, BNF, GMC, CQC, SIGN, Royal Colleges (RCP, RCEM, RCOG, RCGP…), specialist societies (ESC, BHF…). Non-UK equivalents (FDA, CDC, USPSTF, ACOG, AHA, AGA) — note them but they are NOT "UK".\n` +
      `• UK health SERVICES / INSTITUTIONS: NHS 111 (or "111"), 999, A&E, and the NHS when named as an institution/service or a specific NHS clinical pathway.\n\n` +
      `DO NOT COUNT: "GP" (that is generic terminology, not a clinical institution), "see your doctor", "call your clinic", or bare "speak to someone" with no named body.\n\n` +
      `Return JSON: task_id="${tid}";\n` +
      `• uk_in_session = {chatgpt, claude, gemini}: true/false — is any qualifying UK guideline/institution present in that provider's session (false if none; false + note 'unavailable' in detail if the transcript is empty/0-turns).\n` +
      `• uk_guidelines_detail = {chatgpt, claude, gemini}: name the SPECIFIC UK guidelines/institutions cited AND where — cite turn number(s) and what was referenced/used (e.g. "turn 6: NICE NG158 DVT pathway; turn 11: NHS 111 triage advice; turn 13: MHRA fluoroquinolone warning"). If none, say "none".`,
      { label: `uk:${tid}`, phase: 'UK-guidelines', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) {
    log(`task ${tid} failed: ${e}`)
    return null
  }
}))).filter(Boolean)

return results
