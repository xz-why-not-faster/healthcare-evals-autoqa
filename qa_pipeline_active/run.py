#!/usr/bin/env python3
"""run.py — one entrypoint for the daily L1 AutoQA run.

The pipeline interleaves deterministic Python steps with LLM eval steps that run inside
the Claude Code Workflow runtime (the eval `.js` files). Python can't trigger a Workflow —
an agent does — so the run has TWO checkpoints where you (or an agent following the
`run-l1-eval` skill) run a Workflow, then hand its `.output` back here.

Flow:

    run.py ingest   RUN --csv CSV --ids ids.json     # scaffold + ingest + meta + pdf check
    # ── CHECKPOINT 1: run Workflow build/battery_nt.js  (args = the task ids) → save battery.output
    run.py persist  RUN --output battery.output       # split battery output into phase_*.json
    run.py categorize RUN                              # eval_findings.csv + worklist + backfill/external inputs
    # ── CHECKPOINT 2: run Workflows qa_active_backfill.js, qa_active_revoice.js, qa_active_external.js
    run.py deliverables RUN --csv CSV                  # build every deliverable

RUN may be a bare label (becomes qa_pipeline_active/<label>) or a path. Each command prints
exactly what to do next. See PIPELINE.md for the detail and EVAL_MAP.md / DELIVERABLES.md for
what each eval and deliverable actually does.
"""
import argparse, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))          # qa_pipeline_active/
BUILD = os.path.join(HERE, "build")
PY = sys.executable


def resolve_run(run):
    """Bare label -> qa_pipeline_active/<label>; path -> as given."""
    return run if os.path.sep in run else os.path.join(HERE, run)


def sh(cmd, cwd=None):
    print(f"  $ {' '.join(os.path.relpath(c, HERE) if os.path.isabs(c) else c for c in cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def load_ids(args):
    if args.ids:
        ids = json.load(open(args.ids))
    elif args.tasks:
        ids = [t.strip() for t in args.tasks.split(",") if t.strip()]
    else:
        sys.exit("provide --ids <json array file> or --tasks id1,id2,...")
    if not isinstance(ids, list) or not ids:
        sys.exit("no task ids found")
    return ids


def cmd_ingest(args):
    run = resolve_run(args.run)
    os.makedirs(run, exist_ok=True)
    # 1. drop the build templates into the run folder (they run from here)
    for f in os.listdir(BUILD):
        src = os.path.join(BUILD, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(run, f))
    # 2. the id list every downstream step keys off of
    ids = load_ids(args)
    json.dump(ids, open(os.path.join(run, "pending_ids.json"), "w"), indent=1)
    print(f"[ingest] {len(ids)} task(s) -> {os.path.relpath(run, HERE)}")
    # 3. ingest case files + link status, then meta, then the artifact (PDF-vs-link) check
    ing = [PY, os.path.join(HERE, "ingest_active.py"), "--csv", args.csv, "--run", run,
           "--tasks-file", os.path.join(run, "pending_ids.json"), "--levels", args.levels]
    if args.no_download:
        ing.append("--no-download")
    sh(ing)
    sh([PY, os.path.join(run, "build_meta.py"), args.csv])
    sh([PY, os.path.join(HERE, "pdf_link_check.py"), run])
    print("\n── CHECKPOINT 1 ──────────────────────────────────────────────")
    print("Run the eval battery (Claude Code Workflow):")
    orch = "build/battery_traffic.js" if args.traffic else "build/battery_nt.js"
    print(f'  Workflow scriptPath = qa_pipeline_active/{orch}')
    print(f'  args = {json.dumps(ids)}')
    print(f"Save its .output, then:  run.py persist {args.run} --output <battery.output>")


def cmd_persist(args):
    run = resolve_run(args.run)
    sh([PY, os.path.join(run, "persist_battery.py"), args.output])
    print(f"[persist] phase_*.json written -> next: run.py categorize {args.run}")


def cmd_categorize(args):
    run = resolve_run(args.run)
    sh([PY, os.path.join(run, "categorize.py")])              # eval_findings.csv + worklist.json
    sh([PY, os.path.join(run, "build_worklist.py")])          # backfill plan for the LLM eval
    sh([PY, os.path.join(run, "build_external_input.py")])    # reviewer-facing inputs for the LLM eval
    print("\n── CHECKPOINT 2 ──────────────────────────────────────────────")
    print("Run these Claude Code Workflows over this run's task ids:")
    print("  qa_active_backfill.js  -> phase_backfill.json   (rewrite flagged justifications)")
    print("  qa_active_revoice.js   -> contributor voice pass")
    print("  qa_active_external.js  -> phase_external.json   (reviewer-facing prose)")
    print(f"Then:  run.py deliverables {args.run} --csv <CSV>")


def cmd_deliverables(args):
    run = resolve_run(args.run)
    for script in ("build_melt.py", "build_persona_sheet.py",
                   "build_contributor_feedback.py", "build_disagreements.py"):
        sh([PY, os.path.join(run, script)])
    sh([PY, os.path.join(run, "build_sheets.py"), args.csv])
    print(f"\n[deliverables] see {os.path.relpath(os.path.join(run, 'deliverables'), HERE)}/")


def main():
    ap = argparse.ArgumentParser(description="Daily L1 AutoQA runner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="scaffold run folder + ingest + meta + pdf check")
    p.add_argument("run"); p.add_argument("--csv", required=True)
    p.add_argument("--ids", help="JSON array file of task ids")
    p.add_argument("--tasks", help="comma-separated task ids")
    p.add_argument("--levels", default="L1")
    p.add_argument("--no-download", action="store_true", help="skip live link scrape (use cached transcripts)")
    p.add_argument("--traffic", action="store_true", help="print the traffic battery orchestrator at checkpoint 1")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("persist", help="split a battery .output into phase_*.json")
    p.add_argument("run"); p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_persist)

    p = sub.add_parser("categorize", help="findings + worklist + backfill/external inputs")
    p.add_argument("run"); p.set_defaults(func=cmd_categorize)

    p = sub.add_parser("deliverables", help="build every deliverable")
    p.add_argument("run"); p.add_argument("--csv", required=True)
    p.set_defaults(func=cmd_deliverables)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
