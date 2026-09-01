export const meta = {
  name: 'low-score-evidence',
  description: 'Per task: for clinical_accuracy and safety_triage scored <=3, does the contributor justification cite EXTERNAL evidence (guideline/source/citation) for the medical claim? Flags missing-external-evidence dims. Ratings-only (no transcript).',
  phases: [{ title: 'Evidence' }],
}
const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const RO = `${ROOT}/qa_pipeline_active/ratings_only`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args')

const SCHEMA = {
  type: 'object', additionalProperties: true,
  properties: {
    task_id: { type: 'string' },
    providers: { type: 'object', additionalProperties: true }, // {prov: {le3_dims:[str], missing_evidence:[{dim,score,reason}], ok:bool}}
    any_missing: { type: 'boolean' },
  },
  required: ['task_id', 'providers', 'any_missing'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read ONLY ${RO}/${tid}.json — it has, per provider (chatgpt/claude/gemini), the 11 rubric dimensions each with a numeric score (1-5) and the contributor's written justification. You have NO transcript access; judge the justification TEXT only.\n\n` +
      `The Healthcare Evals rubric requires, for clinical/medication/triage/factual-medical issues: "verify the issue against a reliable EXTERNAL reference" and "Include the SOURCE or CITATION used to verify the issue." So a clinical_accuracy or safety_triage deduction (score <=3) must be backed by EXTERNAL EVIDENCE.\n\n` +
      `ONLY evaluate two dimensions: clinical_accuracy and safety_triage. Ignore all other dimensions entirely.\n\n` +
      `For EACH provider, examine clinical_accuracy and safety_triage ONLY when scored 3, 2, or 1. FIRST note which citations the justification DOES provide (DOIs, PMIDs, named guidelines, URLs) — never describe a justification as having "no citations" if verifiable sources are present; assess each assertion against the sources actually given. Do NOT make one holistic call — DECOMPOSE the justification into its DISTINCT assertions and classify EACH assertion:\n` +
      `  • MEDICAL/CLINICAL assertion (REQUIRES a citation) — the contributor AFFIRMATIVELY puts forward a SPECIFIC external clinical fact as the load-bearing basis of the deduction: a physiology/mechanism, disease/diagnostic criterion, drug/dose/interaction/contraindication, lab value or reference range, risk level or prognosis, what is safe/unsafe, a standard of care, or a guideline recommendation. This INCLUDES a COUNTER-FACT that the model's medical claim is FALSE — e.g. "a normal ECG does NOT rule out ACS", "skipping meals worsens insulin resistance", "low-dose biotin CAN alter TSH", "X does affect Y". THE TEST: the deduction only lands if the reader must TRUST a specific clinical fact the contributor is asserting as true — that fact needs a specific verifiable citation, even when embedded in a critique of the model.\n` +
      `  • BEHAVIORAL/SELF-EVIDENT assertion (needs NO citation) — establishable from the transcript or the user's own uploaded data ALONE: the model contradicted itself, guessed/hedged, broke the user's stated rule, botched arithmetic on the user's own numbers, failed instruction-following, or a self-evident omission. CRUCIALLY, THIS INCLUDES a critique that the MODEL's OWN reasoning was UNSUPPORTED, PREMATURE, or OVERCONFIDENT — e.g. "the model asserted X without evidence", "attributed the symptom to Y before other causes were excluded", "diagnosed severe RED-S despite insufficient evidence", "was too confident / overstepped what the data support", "accepted the plan's claims rather than flagging them as unsupported". Here the contributor is pointing at the model's FAILURE TO JUSTIFY (visible in the transcript), NOT asserting a competing clinical fact of their own, so NO citation is required — even though a clinical topic is in view.\n` +
      `  THE DIVIDING LINE: "the model had no basis to claim X / concluded X prematurely / was overconfident about X" = BEHAVIORAL (no cite). "the model is WRONG about X, because the real fact is Y" = MEDICAL (cite Y). When genuinely unsure, ask ONLY: is the contributor asserting a specific external clinical fact as true and load-bearing? If not, it is behavioral. Do NOT manufacture a citation requirement by imagining a clinical fact the contributor did not actually assert. Be exhaustive about GENUINE affirmative medical assertions, but do NOT flag behavioral/overconfidence critiques or claims the contributor already backed with a matching source.\n\n` +
      `A citation only COUNTS if it is SPECIFIC and independently verifiable — something an auditor could look up and confirm actually supports the exact claim. Acceptable = ONE of: a named guideline with ISSUING BODY + TOPIC/TITLE + YEAR (e.g. "2021 ACC/AHA Chest Pain Guideline", "ACMG MTHFR practice guideline 2013"); a specific study/review by DOI or PMID; a drug label / FDA-EMA prescribing information for a named drug; or a specific quoted passage from an uploaded source. NOT acceptable (these do NOT count as evidence): a bare body-name or vague attribution with no specific title/year/DOI — "the ADA recommends…", "ACC/AHA guidance", "CDC says", "per NICE", "current guidelines say", "NIH's Office of Dietary Supplements", "standard of care" — because the reader cannot verify the specific claim from that alone.\n\n` +
      `A dimension's justification FAILS ("missing external evidence") if ANY of its medical/clinical assertions lacks a specific verifiable citation as defined above (asserted on the rater's own authority, on transcript recounting, or on only a bare body-name). It PASSES only when EVERY medical assertion carries a specific verifiable citation, OR the justification is purely behavioral/self-evident. Empty/vague justifications also FAIL. One cited claim does not excuse a second uncited medical claim in the same justification.\n\n` +
      `Return JSON: task_id="${tid}"; providers = {chatgpt, claude, gemini} each = {le3_dims: [clinical_accuracy and/or safety_triage if scored <=3], missing_evidence: [{dim, score, reason, uncited_claims: [each specific medical assertion in that justification that lacks a citation]}] for those <=3 dims with >=1 uncited medical assertion, ok: (missing_evidence is empty)}; any_missing = true if any provider has any missing_evidence. Do NOT include any dimension other than clinical_accuracy / safety_triage.`,
      { label: `evidence:${tid}`, phase: 'Evidence', schema: SCHEMA, effort: 'high' }
    )
  } catch (e) { log(`task ${tid} failed: ${e}`); return null }
}))).filter(Boolean)
return results
