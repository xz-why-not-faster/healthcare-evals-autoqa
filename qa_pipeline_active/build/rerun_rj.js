export const meta = {
  name: 'rerun-ratings-justif',
  description: 'Re-run ONLY ratings + justif over the L1nt20 110 tasks, with the new red-flag/triage double-check (ratings) and user-side consistency (justif) gates.',
  phases: [{ title: 'Rerun' }],
}
const E = '/Users/xilin.zhou/Documents/task-scraper/qa_pipeline_active/evals'
let ids = args
if (typeof ids === 'string') { try { ids = JSON.parse(ids) } catch (e) {} }

const evals = [
  ['ratings', `${E}/qa_active_ratings.js`],
  ['justif',  `${E}/qa_active_justif.js`],
]

const out = {}
const results = await parallel(evals.map(([name, path]) => async () => {
  const r = await workflow({ scriptPath: path }, ids)
  return [name, r]
}))
for (const [name, r] of results) {
  let recs = r
  if (r && !Array.isArray(r) && r.result) recs = r.result
  out[name] = recs
}
return out
