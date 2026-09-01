export const meta = {
  name: 'citation-verify',
  description: 'For each clinical/safety justification scored <=3 in a backfill, extract every cited source and WEB-VERIFY it: does the source actually exist, and does it genuinely support the specific claim it is attached to? Flags fabricated, wrong, or non-supporting citations.',
  phases: [{ title: 'CiteCheck' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const RUN = (_a && _a.run) ? _a.run : null
if (!RUN) throw new Error('Pass {run, ids} — run must hold phase_backfill.json')
const BF = RUN.startsWith('/') ? `${RUN}/phase_backfill.json` : `${ROOT}/${RUN}/phase_backfill.json`
const taskIds = Array.isArray(_a) ? _a : (_a && _a.ids) ? _a.ids : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args (array, or {run, ids:[...]})')

const CIT = {
  type: 'object', additionalProperties: false,
  required: ['claim', 'citation', 'exists', 'supports', 'verdict', 'note'],
  properties: {
    claim: { type: 'string' },        // the specific medical assertion the citation is meant to back
    citation: { type: 'string' },     // the identifier as written in the justification
    exists: { type: 'boolean' },      // did you confirm the source is real via web search/fetch
    supports: { type: 'boolean' },    // does it genuinely support THIS claim
    verdict: { type: 'string', enum: ['VERIFIED', 'SOURCE_NOT_FOUND', 'DOES_NOT_SUPPORT', 'UNVERIFIABLE'] },
    note: { type: 'string' },         // what you found (title/year confirmed, or why it fails)
  },
}
const DIMOBJ = { type: 'object', additionalProperties: false, required: ['score', 'citations'],
  properties: { score: { type: ['integer', 'string'] }, citations: { type: 'array', items: CIT } } }
const PROV = { type: 'object', additionalProperties: DIMOBJ }
const SCHEMA = { type: 'object', additionalProperties: true, required: ['task_id', 'providers', 'any_bad_citation'],
  properties: { task_id: { type: 'string' }, providers: { type: 'object', additionalProperties: PROV }, any_bad_citation: { type: 'boolean' } } }

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `You are VERIFYING the citations in rewritten rating justifications for one Healthcare Evals task. Read ${BF} and take the object under key "${tid}" -> providers. For EACH provider, look ONLY at the clinical and/or triage justifications whose score is <= 3 (skip overall; skip anything scored >=4; skip providers/dims with no citation).\n\n` +
      `For each such justification: pull out EVERY distinct external source it cites (a DOI, a PMID, a named guideline with body+title+year, or a drug label — e.g. "FDA prescribing information for ibuprofen"), and the SPECIFIC medical claim each source is attached to.\n\n` +
      `For EACH (claim, citation) pair, use WebSearch / WebFetch to check TWO things independently:\n` +
      `  1. EXISTS — is this a real, findable source? Confirm the DOI/PMID resolves, or the named guideline (that exact body + title + year) is real, or the drug label exists. Do NOT trust the identifier on its face — look it up.\n` +
      `  2. SUPPORTS — does that source ACTUALLY support the specific claim it is attached to? A real source cited for a claim it does not actually make is still a bad citation. Read enough of it (title/abstract/label section) to confirm the claim is genuinely backed.\n\n` +
      `Assign a verdict per pair:\n` +
      `  • VERIFIED — source is real AND supports the claim.\n` +
      `  • SOURCE_NOT_FOUND — you could not find this source (likely fabricated/misremembered DOI, PMID, or guideline title/year). exists=false.\n` +
      `  • DOES_NOT_SUPPORT — source is real but does NOT establish the claim it is attached to (wrong paper, over-reach, or the claim is outside the source's scope). exists=true, supports=false.\n` +
      `  • UNVERIFIABLE — you genuinely could not determine either way after a real attempt (say why).\n\n` +
      `Be skeptical and specific: a citation that "looks right" is not verified until you have actually found the source and matched it to the claim. Prefer DOES_NOT_SUPPORT / SOURCE_NOT_FOUND over a charitable VERIFIED when in doubt.\n\n` +
      `Return JSON: task_id="${tid}"; providers = { <provider>: { <clinical|triage that is <=3 and has a citation>: { score:<int>, citations: [ {claim, citation, exists, supports, verdict, note} ] } } }; any_bad_citation = true if ANY pair is SOURCE_NOT_FOUND or DOES_NOT_SUPPORT. Include only providers/dims you actually checked.`,
      { label: `citecheck:${tid}`, phase: 'CiteCheck', schema: SCHEMA, effort: 'high', agentType: 'general-purpose' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
