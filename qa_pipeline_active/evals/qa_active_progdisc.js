export const meta = {
  name: 'progressive-disclosure',
  description: 'Score how well a task follows PROGRESSIVE DISCLOSURE across turns — a simple, natural opening premise that reveals context over the conversation (like a real user), rather than front-loading a ton of context into turn 1 or dumping heavy context into every turn. Rewards realism while keeping complexity.',
  phases: [{ title: 'ProgDisc' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a && _a.ids) ? _a.ids : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args (array, or {ids:[...]})')

const SCORES = {
  type: 'object', additionalProperties: false,
  properties: {
    opening_simplicity: { type: 'integer', minimum: 1, maximum: 5 },       // 5 = simple, natural, single-worry opener; 1 = turn 1 dumps everything
    conversational_disclosure: { type: 'integer', minimum: 1, maximum: 5 }, // 5 = reveals via real dialogue (asks questions, reacts); 1 = each turn just uploads another file
    few_files: { type: 'integer', minimum: 1, maximum: 5 },                 // 5 = mostly talking; attachments are few (roughly 0-3) and well-spaced; 1 = a new file piled on in a large share of turns
    healthcare_relevance: { type: 'integer', minimum: 1, maximum: 5 },      // 5 = core clinical/health task; 1 = not really healthcare (e.g. insurance/billing/admin)
    complexity_maintained: { type: 'integer', minimum: 1, maximum: 5 },     // 5 = still a rich, multi-step task despite the simple opener; 1 = trivial
  },
  required: ['opening_simplicity', 'conversational_disclosure', 'few_files', 'healthcare_relevance', 'complexity_maintained'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    task_id: { type: 'string' },
    verdict: { enum: ['STRONG_EXEMPLAR', 'OK', 'NOT_EXEMPLAR'] },
    scores: SCORES,
    file_turns: { type: 'integer' },                   // how many user turns introduce a NEW attached file
    opening_quote: { type: 'string' },                 // short snippet of the actual opening user message
    dump_turns: { type: 'string' },                    // where files get piled on, or "none"
    one_line: { type: 'string' },                      // one plain-language sentence on why it is / isn't a good example
  },
  required: ['task_id', 'verdict', 'scores', 'file_turns', 'opening_quote', 'dump_turns', 'one_line'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json. Under "providers", each of the three (chatgpt, claude, gemini) has transcript.turns — each turn has "user" (the user's message) and "response" (the model). The three share the same opening premise, so judge PROGRESSIVE DISCLOSURE from the USER side of the conversation (use whichever provider has the most complete transcript).\n\n` +
      `We want tasks that mimic how a real person actually talks to a health chatbot. The gold-standard pattern: OPEN with a simple, natural worry, then mostly TALK — ask follow-up questions, react to answers, add small bits of context in words — like a genuine back-and-forth conversation. Attachments should be MINIMAL (ideally zero or one, referenced naturally).\n\n` +
      `Two failure modes to penalize hard:\n` +
      `1) FILE-PILING: the user keeps uploading a NEW document almost every turn (food log, then weight app, then a physical, then an NIH sheet, then a plan...). Even though it's spread out, real users do not do this — it is unnatural context stacking, not conversation. Few files = good; a new file nearly every turn = bad.\n` +
      `2) NOT HEALTHCARE: the task is really insurance / billing / benefits / admin rather than a clinical or health question. That is not what we want, no matter how well-paced.\n\n` +
      `GOLD example (score it high): a college freshman gets one fitness assessment, opens by asking to understand it, then just asks natural questions turn after turn ("what does VO2 max mean for me?", "what about my resting heart rate?", "what do you recommend?") with NO further file uploads — pure curious dialogue that still builds to a real plan.\n` +
      `BAD example: opens with a symptom but then attaches a food log, a weight-app export, a past physical, an NIH page, and a training plan across successive turns (file-piling); OR an open-enrollment "which insurance plan should I pick" cost comparison (not healthcare).\n\n` +
      `Score each 1-5 (5 best): opening_simplicity (simple natural single-worry opener vs turn-1 dump); conversational_disclosure (reveals through real dialogue/questions vs each turn just uploads another file); few_files (0-1 attachments total vs a new file piled on almost every turn); healthcare_relevance (core clinical/health task vs insurance/billing/admin); complexity_maintained (still a rich multi-step task, not trivial).\n\n` +
      `verdict: STRONG_EXEMPLAR (simple opener, mostly conversational, few/no files, genuinely clinical, still substantive — a task you'd proudly show as the target), OK (decent but flawed, e.g. a couple of files or a slightly admin premise), NOT_EXEMPLAR (file-piling, or not really healthcare, or trivial).\n\n` +
      `Return JSON: task_id="${tid}"; verdict; scores{...}; file_turns = the count of user turns that introduce a NEW attached file; opening_quote = a short verbatim snippet of the actual first user message; dump_turns = a brief note of the turns that pile on files (or "none"); one_line = one plain sentence, reviewer-facing, on why this is or isn't a good example.`,
      { label: `progdisc:${tid}`, phase: 'ProgDisc', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
