export const meta = {
  name: 'revoice-justifications',
  description: 'Re-voice the rewritten backfill justifications to sound like the CONTRIBUTOR who wrote the original — match their length, plainness and word-choice, reuse their phrasing, strip AI tells — while keeping the corrected facts, score, and any verified citation. Never reintroduce a claim the transcript contradicts.',
  phases: [{ title: 'ReVoice' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const RUN = (_a && _a.run) ? _a.run : null
if (!RUN) throw new Error('Pass {run, ids} — run holds phase_backfill.json and worklist.json')
const base = RUN.startsWith('/') ? RUN : `${ROOT}/${RUN}`
const BF = `${base}/phase_backfill.json`
const WL = `${base}/worklist.json`
const taskIds = Array.isArray(_a) ? _a : (_a && _a.ids) ? _a.ids : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args (array, or {run, ids:[...]})')

const SCHEMA = {
  type: 'object', additionalProperties: true,
  properties: { task_id: { type: 'string' }, providers: { type: 'object', additionalProperties: true } },
  required: ['task_id', 'providers'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `You are RE-VOICING corrected rubric justifications for ONE Healthcare Evals task so they sound like the HUMAN CONTRIBUTOR who wrote the originals — not like an AI. Read:\n` +
      `1) ${WL} — key "${tid}": per provider, orig = the contributor's ORIGINAL overall/clinical/triage justification (THIS IS YOUR VOICE ANCHOR), and fixes = which dims were rewritten (needs_rewrite=true) and the kept target_score.\n` +
      `2) ${BF} — key "${tid}" -> providers: the CURRENT rewritten justification for each of those dims. This version has the CORRECT facts, turn references, score alignment, and any verified citation — but it reads like polished AI prose.\n` +
      `3) ${WS}/task_${tid}.json — the transcripts, so you stay factually grounded.\n\n` +
      `Your job: for EACH dim where fixes.<dim>.needs_rewrite is true, START FROM THE CONTRIBUTOR'S ORIGINAL justification (orig) and make the SMALLEST possible set of edits to it — this is a surgical edit of THEIR text, not a rewrite. The current rewrite in phase_backfill is only your reference for WHAT IS TRUE (the corrected facts, the turn citations, the fixed score, and any verified external citation); do NOT copy its wording or structure. The output should read as if the contributor themselves lightly edited their own note.\n\n` +
      `THE METHOD — be aggressive about preserving the original:\n` +
      `  • DEFAULT TO VERBATIM. Keep the contributor's original sentences word-for-word wherever the point they made is still true. Only touch the specific clause that (a) the transcript CONTRADICTS, (b) needs a citation added, or (c) must change to match the corrected score. Leave everything else exactly as they wrote it.\n` +
      `  • PRESERVE THEIR EXACT STYLE — their word choices ("the assistant", "the model", "AI engine" — whatever THEY used), their sentence length, their punctuation and capitalization habits, and even mild grammatical looseness or terseness. Do NOT smooth, polish, expand, or "improve" their prose. If they wrote one blunt sentence, you return one blunt sentence (plus only what a correction strictly requires).\n` +
      `  • LENGTH ANCHOR — stay as close to the ORIGINAL length as possible. A one-line original stays roughly one line. Adding a citation or fixing a false clause may add a few words; it must NOT turn a sentence into a paragraph. When in doubt, cut.\n` +
      `  • If a contradicted clause has to go, delete or minimally correct it in place — do not replace it with a longer, more elaborate description than the contributor would have written.\n\n` +
      `NEVER introduce AI tells that were not in the original: the "X is strong: a, b, and c" colon+triad scaffold; em-dash dramatic asides; stock evaluative phrases ("A capable, safety-minded session", "What holds it back from a higher mark", "genuinely useful", "carefully reasoned", "thoughtful", "measured", "to its credit", "that said", "makes the experience worth a 2"); balanced tricolons; windup openers that restate the whole session before the point; or elevated diction in place of a plain word. If the contributor's original had none of these, yours has none.\n\n` +
      `HARD CONSTRAINTS:\n` +
      `  • Do NOT change the score. Keep it consistent with fixes.<dim>.target_score, exactly as the current rewrite is.\n` +
      `  • Do NOT reintroduce any claim the current rewrite removed — those were removed because the transcript CONTRADICTS them. Stay factually identical to the current (correct) rewrite; you are only changing HOW it is said.\n` +
      `  • KEEP every citation exactly as in the current rewrite (same DOI/PMID/guideline/label identifier, inline where it was). Voice never overrides sourcing. If the current version cites a source, the re-voiced version cites the same source.\n` +
      `  • Overall justifications: still never mention gating/caps/scoring mechanics.\n\n` +
      `Return JSON: task_id="${tid}"; providers = { <provider>: { <only the re-voiced dims — use the EXACT fixes key for each (any of the 11 rubric dims: overall, clinical_accuracy, safety_triage, completeness, communication_tone, instruction_following, interaction_efficiency, multimodal_fidelity, personal_context, ui_experience, worth_using_again)>: { score:<number as string, unchanged>, justification:<the re-voiced text>, citation:<the SAME citation string as the current rewrite, or ""> } } }. Include only the dims you re-voiced (the needs_rewrite ones).`,
      { label: `revoice:${tid}`, phase: 'ReVoice', schema: SCHEMA, effort: 'high', agentType: 'general-purpose' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
