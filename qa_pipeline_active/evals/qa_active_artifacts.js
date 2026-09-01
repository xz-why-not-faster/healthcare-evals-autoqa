export const meta = {
  name: 'artifact-validity',
  description: 'Per task, per model: did the contributor upload the artifacts the session generated? (session_artifact_issues yes/no/n-a).',
  phases: [{ title: 'Artifacts' }],
}

const ROOT = '/Users/xilin.zhou/Documents/task-scraper'
const WS = `${ROOT}/qa_pipeline_active/workspace`
let _a = args
if (typeof _a === 'string') { try { _a = JSON.parse(_a) } catch (e) {} }
const taskIds = Array.isArray(_a) ? _a : (_a ? [_a] : [])
if (!taskIds.length) throw new Error('Pass task id(s) as args')

const SCHEMA = {
  type: 'object', additionalProperties: true,
  properties: {
    task_id: { type: 'string' },
    task_artifact_verdict: { type: 'string', enum: ['OK', 'ISSUES', 'N/A'] },
    models: { type: 'object', additionalProperties: true },
  },
  required: ['task_id', 'task_artifact_verdict', 'models'],
}

const results = (await parallel(taskIds.map((tid) => async () => {
  try {
    return await agent(
      `Read the case file at ${WS}/task_${tid}.json. Per provider (chatgpt/claude/gemini) it has: the full transcript turns (user + response); links.session_artifacts and artifacts.session_artifacts (the files the contributor UPLOADED as "the artifacts this session generated", each with a local downloaded "path", "bytes", "ctype"); plus session_pdf / model_screenshot / tier_screenshot / artifacts_throughout as supporting context.\n\n` +
      `You are auditing ONE question per model: DID THE CONTRIBUTOR UPLOAD THE ARTIFACTS THAT THE SESSION ACTUALLY GENERATED?\n\n` +
      `Procedure for EACH provider:\n` +
      `1. session_generated_artifacts — read the transcript and determine whether the MODEL actually produced/generated a downloadable or rendered FILE/DOCUMENT during the session (e.g. a PDF/CSV/spreadsheet/chart/image/canvas document it says it "created", "put together", "generated", "here is your…", a downloadable link, a rendered table meant to be exported). List each as {what, turn, evidence(short quote)}. If the model only gave prose advice and generated NO file, set any=false — nothing was owed.\n` +
      `2. uploaded_session_artifacts — inspect what is actually in session_artifacts: count, and per file {ctype, bytes, looks_like}. OPEN/READ the downloaded file at its "path" to say what it actually is (e.g. PDF: read text; CSV: read rows; PNG: note it's an image). If the path is missing/zero bytes, say so.\n` +
      `3. Compare: is every generated artifact from step 1 present and represented in the uploaded session_artifacts (matching kind/content)? A generated file that is missing from the upload, or an uploaded file that plainly is NOT the generated artifact (e.g. only a screenshot uploaded in place of the actual generated PDF, or an empty/zero-byte file, or an unrelated file), is an issue.\n\n` +
      `Set session_artifact_issues per model: "yes" (a generated artifact is missing from the upload, or the upload clearly is not that artifact), "no" (the session generated artifact(s) and they were all uploaded and match), or "n/a" (the session generated no artifact, so nothing was owed). detail = one line citing the turn and the uploaded file.\n\n` +
      `NOTE: session_artifacts is the ONLY deliverable under audit here. Do NOT flag missing screenshots/session_pdf as artifact issues (those are separate deliverables). If a transcript is empty/unavailable, set that model session_artifact_issues="n/a", detail="transcript unavailable".\n\n` +
      `VOICE: "detail" is reviewer-facing. Write it in the third person — refer to the model by name (ChatGPT/Claude/Gemini), never use "I"/"we"/"my". Quote transcript/file text verbatim.\n\n` +
      `Return JSON: task_id="${tid}"; task_artifact_verdict = "ISSUES" if any model is "yes", else "N/A" if all three are "n/a", else "OK"; models = {chatgpt, claude, gemini} each = {session_artifact_issues, session_generated_artifacts:{any, items:[{what,turn,evidence}]}, uploaded_session_artifacts:{count, files:[{ctype,bytes,looks_like}]}, detail}.`,
      { label: `artifacts:${tid}`, phase: 'Artifacts', schema: SCHEMA, effort: 'medium' }
    )
  } catch (e) {
    log(`task ${tid} failed: ${e}`)
    return null
  }
}))).filter(Boolean)

return results
