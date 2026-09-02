export const meta = {
  name: 'pdf-recheck',
  description: 'LLM second pass on deterministic wrong_pdf flags: is the uploaded chat PDF the SAME conversation as the live share link, or genuinely a DIFFERENT one? Conservative — clears false positives (image-rendered / garbled PDFs).',
  phases: [{ title: 'PDF recheck' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) {} }
let RUN = (A && A.run) ? A.run : `${ROOT}/qa_pipeline_active`
if (!RUN.startsWith('/')) RUN = `${ROOT}/${RUN}`
const taskIds = Array.isArray(A) ? A : (A && A.ids) ? A.ids : (A ? [A] : [])
if (!taskIds.length) throw new Error('Pass {run, ids:[...]} — each agent reads <run>/verify/pdf/<tid>.json')

const SCHEMA = { type: 'object', additionalProperties: false,
  required: ['task_id', 'providers'],
  properties: { task_id: { type: 'string' },
    providers: { type: 'object' } } }   // {prov: {verdict: SAME_CONVO|WRONG_CONVO|UNVERIFIABLE, confidence, reasoning}}

const results = await parallel(taskIds.map((tid) => async () => agent(
  `Re-check a deterministic wrong_pdf flag. Read ${RUN}/verify/pdf/${tid}.json — an object {task_id, providers:{<prov>:{live_user_turns, pdf, pdf_only_headers}}}. Only the flagged provider(s) are present.\n\n` +
  `For EACH provider, decide whether the uploaded chat PDF is the SAME conversation as the live share link, or an ENTIRELY DIFFERENT one. Truncation, reformatting, image-rendering (pdf_only_headers=true means only page-header/screenshot noise extracted), garbled extraction, or a title/header line are NOT errors — only a genuinely DIFFERENT conversation about a DIFFERENT topic is.\n\n` +
  `- SAME_CONVO: the PDF text (title, topic, any readable phrase) is consistent with the live user turns' subject.\n` +
  `- WRONG_CONVO: the PDF clearly contains a DIFFERENT conversation about a DIFFERENT topic than the live turns. Cite the concrete different-topic phrase.\n` +
  `- UNVERIFIABLE: image-rendered / only headers / too garbled to read any topic — cannot confirm either way. DEFAULT to this over WRONG_CONVO when unsure.\n\n` +
  `Be conservative: only WRONG_CONVO when you can point to concrete different-topic content. Return {task_id:"${tid}", providers: { <prov>: {verdict, confidence: high|medium|low, reasoning: 1-2 sentences citing the specific PDF phrase vs the live topic} }} for each provider in the input.`,
  { label: `pdfrecheck:${tid.slice(-6)}`, phase: 'PDF recheck', schema: SCHEMA, effort: 'low' })))
return results
