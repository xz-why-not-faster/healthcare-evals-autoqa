export const meta = {
  name: 'user-voice',
  description: 'Every task is DESIGNED to be a patient (or their close family). Judge how the patient TALKS: like a real layperson, or using too much medical speak (clinical shorthand like "53F"/"SDEC"/"2/7", fluent recitation of exact labs + reference ranges, technical jargon a normal person would not use, or third-person case-presentation framing). Used to filter progressive-disclosure exemplars to genuine real-user register.',
  phases: [{ title: 'Voice' }],
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
    verdict: { enum: ['natural', 'some_medical_speak', 'too_much_medical_speak'] },
    layperson_score: { type: 'integer', minimum: 1, maximum: 5 },  // 5 = talks like a real patient; 1 = talks like a clinician
    clinical_shorthand: { type: 'boolean' },   // "53F", "SDEC", "2/7", "hx of", "pt", drug abbreviations
    recites_precise_labs: { type: 'boolean' }, // reads out exact values + units + reference ranges fluently, like reading a chart
    third_person_case: { type: 'boolean' },    // presents it as a case ("A 78yo man who...") rather than living it
    tells: { type: 'string' },                 // the specific medical-speak phrases, or "none"
    opening_quote: { type: 'string' },
    one_line: { type: 'string' },
  },
  required: ['task_id', 'verdict', 'layperson_score', 'clinical_shorthand', 'recites_precise_labs', 'third_person_case', 'tells', 'opening_quote', 'one_line'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json. Under "providers", each has transcript.turns with "user" messages. Judge the USER register across the conversation (use whichever provider is most complete).\n\n` +
      `ASSUME EVERY TASK IS DESIGNED TO BE A PATIENT (or a close family member helping) — that is not in question. The question is HOW the patient talks. We want patients who sound like real laypeople; we want to flag ones who use too much MEDICAL SPEAK.\n\n` +
      `TOO MUCH MEDICAL SPEAK (flag it) looks like:\n` +
      `- clinical shorthand a normal person wouldn't write: "53F", "SDEC", "2/7", "hx of", "pt", "BID", casually abbreviated drugs/labs;\n` +
      `- reading out exact lab values with units AND reference ranges fluently, like reciting a chart ("TSH was 1.60 and free T4 was 1.26, both within the lab range; vitamin D 29.4 ng/mL");\n` +
      `- technical terminology a layperson wouldn't reach for unprompted ("proximal leg weakness", "endometrial hyperplasia", "venous thromboembolism", "post-EVAR");\n` +
      `- third-person case-presentation framing ("A 78 year old frail man who suffered an acute kidney injury...") instead of living it.\n\n` +
      `NATURAL (good) looks like: plain-language symptoms and worries ("I've been really tired and foggy", "my thyroid number came back a bit high, is that bad?", "I had surgery two weeks ago and want to heal right"), asking what things mean for them, everyday wording. A patient can mention a real lab result naturally — the flag is for sustained clinician-grade precision/jargon, not one plain number.\n\n` +
      `verdict: "natural" (reads like a real patient throughout), "some_medical_speak" (mostly natural but a few clinician-ish moments), "too_much_medical_speak" (sustained jargon/shorthand/chart-reciting, or a third-person case opener). layperson_score 1-5 (5 = fully natural patient, 1 = fully clinician).\n\n` +
      `Return JSON: task_id="${tid}"; verdict; layperson_score; clinical_shorthand; recites_precise_labs; third_person_case; tells = the specific medical-speak phrases (or "none"); opening_quote = short verbatim snippet of the first user message; one_line = one plain sentence on why.`,
      { label: `voice:${tid}`, phase: 'Voice', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
