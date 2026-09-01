export const meta = {
  name: 'rerun-justif-only',
  description: 'Re-run ONLY justif over a small task list to test valid_model_stump stability (non-determinism check).',
  phases: [{ title: 'Rerun' }],
}
const E = '/Users/xilin.zhou/Documents/task-scraper/qa_pipeline_active/evals'
let ids = args
if (typeof ids === 'string') { try { ids = JSON.parse(ids) } catch (e) {} }
const r = await workflow({ scriptPath: `${E}/qa_active_justif.js` }, ids)
let recs = r
if (r && !Array.isArray(r) && r.result) recs = r.result
return { justif: recs }
