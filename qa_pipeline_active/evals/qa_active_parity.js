export const meta = {
  name: 'healthcare-evals-parity',
  description: 'Improved intent/parity check only (turn-alignment + attachment-timing + opening-prompt) — no structural/ratings.',
  phases: [{ title: 'Parity' }],
}

const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
const SK = `${ROOT}/.claude/skills`
const RUBRIC = `${SK}/qa-shared/rubric.md`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args')

const S_PARITY = { type: 'object', additionalProperties: true, properties: { task_id: { type: 'string' }, verdict: { type: 'string', enum: ['PASS', 'FAIL'] }, severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'none'] }, per_provider_intent: { type: 'object', additionalProperties: true }, issues: { type: 'array', items: { type: 'string' } } }, required: ['task_id', 'verdict', 'severity', 'issues'] }

phase('Parity')
const results = (await parallel(taskIds.map((tid) => async () => {
  const caseFile = `${WS}/task_${tid}.json`
  const base = `Read the rubric at ${RUBRIC} and the case file at ${caseFile}. It has, per provider, the transcript turns, all links, downloaded artifacts, and a precomputed "gates" block.`
  try {
    const p = await agent(
        `${base}\nFollow ${SK}/qa-intent-parity/SKILL.md EXACTLY, reading each transcript's CONTENT turn by turn. You MUST do: (2a) OPENING-PROMPT parity — if the opening user prompt is NOT the same across the 3 providers (one model got a reworded/different opening question, after stripping [attached:] annotations), that is a PARITY break; (2b) align the USER turns by position and flag needless deviations — a wording tweak added to some models not others, an extra ask given to some but not all, or an offset/duplicated/fragment user turn; (2c) check attachment TIMING — flag when a file others attached at the opening is missing from one model's first prompt and added later (only Gemini annotates [attached:]; for ChatGPT/Claude infer an attachment ONLY from response content UNIQUE to that specific file — NEVER from data that also appears in another document that model did receive). PUNT RULE: a single model that REFUSES/PUNTS does NOT break parity — evaluate the engaged models and NOTE the punt. Fail parity for a real divergence (different opening prompt across providers, wrong/mismatched conversation, missing key input, unmatched intent/end-state); report turn-alignment and attachment-timing deviations as issues even when minor.\n\n` +
        `SEVERITY↔VERDICT CONSISTENCY (MANDATORY, no exceptions): the verdict MUST follow the severity. If severity is "blocker" or "major", verdict MUST be "FAIL" — you may NOT return {verdict:"PASS", severity:"major"}. Only "minor" or "none" severity may pair with "PASS". If you find yourself wanting to call something "major" but still pass it, either it is truly minor (downgrade the severity) or it is a real break (FAIL) — pick one; do not split the difference.\n\n` +
        `END-STATE / REVIEWABLE-RECORD RULE (this is what "major" means here): the shared final deliverable must be REACHED and VISIBLE in EACH provider's reviewable transcript. If the deliverable-generating turn is present in only some providers' share links (e.g. one transcript terminates before the artifact-generation request while another shows it), that is a MAJOR end-state parity break → FAIL. Do NOT excuse a missing deliverable turn on the grounds that an artifact/PDF is ATTACHED to the case file — an attachment you cannot see produced in the transcript is NOT evidence the turn happened, and if anything the record cannot establish parity, which is itself the failure. "The first N turns are lockstep-identical" does NOT rescue a trajectory that stops before the deliverable in one provider.\n\n` +
        `INPUT-PARITY / NO-INFERRED-RECEIPT RULE (MANDATORY — this is the missing-key-input case the severity rule exists to enforce; it applies to INPUTS the same way the end-state rule applies to deliverables): FIRST build, per provider, the SET of distinct source documents that model was actually GIVEN. Count a document as GIVEN only when a user turn explicitly presents it (Gemini via [attached:]; ChatGPT/Claude via a user turn that hands it over) AND, for ChatGPT/Claude, the response reflects content UNIQUE to that document. If a distinct key document is present for some providers but ABSENT for another, that is an INPUT-PARITY break → severity major → FAIL. You may NOT rationalize the gap away by inferring the deprived model "received it anyway": data that ALSO appears in a DIFFERENT document that model did receive is NOT evidence it saw the missing one (e.g. an LSI / hop-battery value that appears in BOTH a functional-test sheet AND a PT progress note does NOT prove the model that only uploaded the test also got the note). Only the IDENTICAL document, verifiably delivered elsewhere in THAT SAME transcript, rescues it. Treat the break as MORE serious, never less, when (i) the missing document CONFLICTS with one the model did receive (so the deprived model reasons from a contradictory input set and its advice diverges), or (ii) a user turn keyed to the missing document exists for some providers but not the one lacking it (e.g. "so small jumps are allowed?" present for two providers, absent for the third that never got the clearance note). A smaller input set for one provider is by definition not a valid parallel comparison.\n\n` +
        `Return the skill's JSON, and you MUST include task_id="${tid}" as a field so the result is self-identifying.`,
        { label: `parity:${tid}`, phase: 'Parity', schema: S_PARITY, effort: 'high' }
      )
    // Safety net: severity>=major must imply FAIL, regardless of what the model returned.
    if (p && (p.severity === 'major' || p.severity === 'blocker') && p.verdict !== 'FAIL') {
      p.issues = p.issues || []
      p.issues.unshift(`AUTO-COERCED verdict PASS->FAIL: severity="${p.severity}" cannot pass parity.`)
      p.verdict = 'FAIL'
    }
    return { tid, parity: p }
  } catch (e) {
    log(`task ${tid} failed: ${e}`)
    return null
  }
}))).filter(Boolean)

return results
