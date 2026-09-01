export const meta = {
  name: 'battery-L1nt-13',
  description: 'Full 8-eval battery (incl persona) over L1 non-traffic tasks',
  phases: [{ title: 'Battery' }],
}
const E = '/Users/xilin.zhou/Documents/task-scraper/qa_pipeline_active/evals'
let ids = args
if (typeof ids === 'string') { try { ids = JSON.parse(ids) } catch (e) {} }

const evals = [
  ['parity',    `${E}/qa_active_parity.js`],
  ['ratings',   `${E}/qa_active_ratings.js`],
  ['justif',    `${E}/qa_active_justif.js`],
  ['evidence',  `${E}/qa_active_evidence.js`],
  ['low_effort',`${E}/qa_active_lowffort.js`],
  ['detectors', `${E}/qa_active_detectors.js`],   // = uk + misc + persona + progdisc in ONE transcript read
]

const out = {}
const results = await parallel(evals.map(([name, path]) => async () => {
  const r = await workflow({ scriptPath: path }, ids)
  return [name, r]
}))
for (const [name, r] of results) {
  let recs = r
  if (r && !Array.isArray(r) && r.result) recs = r.result
  if (name === 'parity' && Array.isArray(recs)) {
    recs = recs.map((rec) => (rec && rec.parity ? rec : { tid: rec.task_id, parity: rec }))
  }
  if (name === 'detectors' && Array.isArray(recs)) {
    // split the combined detector output back into the 4 phase keys, each keyed by task_id
    out.uk = recs.map((d) => ({ task_id: d.task_id, ...d.uk }))
    out.misc = recs.map((d) => ({ task_id: d.task_id, ...d.misc }))
    out.persona = recs.map((d) => ({ task_id: d.task_id, ...d.persona }))
    out.progdisc = recs.map((d) => ({ task_id: d.task_id, ...d.progdisc }))
    continue
  }
  out[name] = recs
}
return out
