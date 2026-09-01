export const meta = {
  name: 'low-effort-justifications',
  description: 'Task-level check: are the contributor\'s rating justifications, taken as a whole across all 3 providers x 11 dims, low-effort — phoned-in one-liners / anchor-word restatements / "N/A" placeholders, and/or sloppy writing (typos, grammar errors)? A low_effort task needs its whole rating pass rewritten, not a targeted fix.',
  phases: [{ title: 'LowEffort' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a && _a.ids) ? _a.ids : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args (array, or {ids:[...]})')

const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    task_id: { type: 'string' },
    low_effort: { type: 'boolean' },              // is the rating pass low-effort as a whole?
    reason: { type: 'string' },                    // one-line why
    content_weak: { type: 'boolean' },             // one-liners / anchor restatements / "N/A" dominate
    writing_weak: { type: 'boolean' },             // typos / grammar errors / sloppy phrasing throughout
    weak_count: { type: 'integer' },               // approx # of the 33 justifications that are low-effort
    examples: { type: 'array', items: { type: 'string' } }, // a few "provider dim: <quote>" samples
  },
  required: ['task_id', 'low_effort', 'reason', 'content_weak', 'writing_weak'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json. Under "providers", each of the three (chatgpt, claude, gemini) has "ratings" — the 11 rubric dimensions (overall, clinical_accuracy, safety_triage, completeness, communication_tone, instruction_following, interaction_efficiency, multimodal_fidelity, personal_context, ui_experience, worth_using_again), each with a numeric "score" and the contributor's written "justification".\n\n` +
      `Your ONE job: judge whether the contributor's justifications, taken as a WHOLE across all 3 providers x 11 dimensions (~33 justifications), are LOW-EFFORT — i.e. the rating pass was phoned in and the whole thing needs rewriting, not a targeted fix. This is a holistic, task-level call — do NOT flag individual dimensions.\n\n` +
      `Weigh TWO signals:\n` +
      `(1) CONTENT weakness — the justifications are mostly: bare one-liners; restatements of the rubric anchor word ("Excellent.", "Materially accurate.", "Efficient.", "Recommended", "Ambivalent"); "N/A" / blank placeholders; or generic filler that never points to a specific turn, behavior, quote, or piece of evidence in the actual conversation. Set content_weak=true when this pattern dominates.\n` +
      `(2) WRITING weakness — pervasive typos, grammatical errors, subject-verb disagreement, missing plurals, sloppy phrasing (e.g. "Ever instruction followed", "All part fully addressed", "very minor cosmetics flaws"). Set writing_weak=true when this is widespread across the justifications.\n\n` +
      `Decide low_effort = true when the rating pass as a whole is clearly phoned-in. Either signal can be forgivable alone (a genuinely flawless session can warrant brief justifications; a non-native writer can still do thorough, specific work) — but when MOST of the ~33 justifications are one-liners/anchor-restatements/"N/A" AND/OR the writing is sloppy throughout, that is low_effort=true. A task with substantive, transcript-grounded justifications for its non-trivial scores is low_effort=false even if a few dims are short.\n\n` +
      `Return JSON: task_id="${tid}"; low_effort (bool); reason (one sentence); content_weak (bool); writing_weak (bool); weak_count (approx how many of the ~33 justifications are low-effort); examples (3-5 strings like "claude safety_triage: 'Every red flags were caught'").`,
      { label: `lowffort:${tid}`, phase: 'LowEffort', schema: SCHEMA, effort: 'low' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
