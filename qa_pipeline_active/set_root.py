#!/usr/bin/env python3
"""One-time setup: point every Workflow eval + orchestrator at THIS checkout.

The eval scripts run inside the Claude Code Workflow runtime, which has no access to
environment variables or the filesystem, so the repo path is baked in as a top-of-file
`const ROOT = '...'` constant. After cloning, run this once to rewrite that constant (and
the derived `const E = '<ROOT>/qa_pipeline_active/evals'` in the battery orchestrators) to
wherever you put the repo.

    python3 qa_pipeline_active/set_root.py            # auto-detect (recommended)
    python3 qa_pipeline_active/set_root.py /abs/path  # or pass the repo root explicitly

Idempotent: safe to run repeatedly. Prints every file it changed.
"""
import os, re, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))          # .../qa_pipeline_active
DEFAULT_ROOT = os.path.dirname(HERE)                        # repo root
root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ROOT

if not os.path.isdir(os.path.join(root, "qa_pipeline_active", "evals")):
    sys.exit(f"[set_root] {root!r} does not look like the repo root "
             f"(no qa_pipeline_active/evals). Pass the correct path.")

targets = sorted(glob.glob(os.path.join(HERE, "evals", "*.js")))
# orchestrators (battery_*, rerun_*) live in build/; legacy stragglers may sit at repo root
targets += sorted(glob.glob(os.path.join(HERE, "build", "*.js")))
targets += sorted(glob.glob(os.path.join(root, "*.js")))

ROOT_RE = re.compile(r"const ROOT = '[^']*'")
E_RE    = re.compile(r"const E = '[^']*/qa_pipeline_active/evals'")

changed = 0
for f in dict.fromkeys(targets):          # dedupe, keep order
    src = open(f).read()
    new = ROOT_RE.sub(f"const ROOT = '{root}'", src)
    new = E_RE.sub(f"const E = '{root}/qa_pipeline_active/evals'", new)
    if new != src:
        open(f, "w").write(new)
        changed += 1
        print(f"  updated {os.path.relpath(f, root)}")

print(f"[set_root] root = {root}")
print(f"[set_root] {changed} file(s) updated; {len(set(targets))} scanned.")
