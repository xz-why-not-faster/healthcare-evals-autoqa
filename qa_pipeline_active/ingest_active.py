#!/usr/bin/env python3
"""
ingest_active.py — one live scrape pass that produces everything the active pipeline needs
for a set of tasks (typically the NEW + re-attempt tasks a run must evaluate).

Per task, per provider it loads the share link ONCE and writes:
  workspace/task_<task_id>.json          the case file (exact active schema; evals read this)
  <txt-dir>/<attempt_id>_<provider>.txt   the human-readable transcript extraction (named by ATTEMPT id,
                                          all in one shared folder)
  artifacts/<task_id>/<provider>/...      downloaded "produced artifacts" (for the phase-3a eval)
and accumulates, into the run folder:
  turns_summary.json    per task: urls/turns/valid/status/detail/all_valid (phase-1 link check)
  sheet_tasks.json      per task: identity + country + session links + taxonomy_type + provider_1/2/3

Usage:
  python ingest_active.py --csv <input.csv> --run <run-folder> [--tasks id1,id2 | --tasks-file f]
                          [--txt-dir qa_pipeline_active/transcripts] [--no-download]
"""
import argparse, csv, json, os, sys, urllib.request
from collections import OrderedDict, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# link-checking + transcript-export helpers live in qa_pipeline_active/lib/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from transcript_exporter import Browser, extract_url, platform_of  # noqa: E402
from link_check import classify, clean  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.join(HERE, "workspace")
ART_DIR = os.path.join(HERE, "artifacts")
PROVIDERS = ("chatgpt", "claude", "gemini")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

RATING_COLS = {
    "overall rating": "overall", "clinical accuracy": "clinical_accuracy",
    "completeness quality": "completeness", "communication tone": "communication_tone",
    "instruction following": "instruction_following", "interaction efficiency": "interaction_efficiency",
    "multimodal fidelity": "multimodal_fidelity", "personal context": "personal_context",
    "safety triage": "safety_triage", "ui experience": "ui_experience", "worth using again": "worth_using_again",
}
SHARED_COLS = ["persona", "modality", "tier", "task category", "prompt",
               "user scenario", "desired end state", "trajectory plan"]


def split_links(cell):
    return [u for u in (cell or "").replace(",", " ").split() if u.startswith("http")]


def parse_uploads(cell):
    """Parse an artifacts cell into [{url, name, mimeType, bytes}].
    New format = a JSON array of file objects (name/s3Url/url/mimeType/fileSizeInBytes);
    old format = whitespace/comma-separated URLs. Falls back to split_links."""
    cell = (cell or "").strip()
    if cell.startswith("["):
        try:
            out = []
            for o in json.loads(cell):
                if not isinstance(o, dict):
                    continue
                u = o.get("s3Url") or o.get("url") or o.get("cdsUrl") or ""
                if u:
                    out.append({"url": u, "name": o.get("name", ""),
                                "mimeType": o.get("mimeType", ""), "bytes": o.get("fileSizeInBytes")})
            return out
        except Exception:
            pass
    return [{"url": u, "name": u.split("/")[-1], "mimeType": "", "bytes": None} for u in split_links(cell)]


def download(url, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    name = url.split("/")[-1].split("?")[0] or "file"
    path = os.path.join(dest_dir, name[:120])
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        open(path, "wb").write(data)
        return {"url": url, "saved": os.path.relpath(path, HERE), "bytes": len(data), "status": 200}
    except Exception as e:
        return {"url": url, "saved": None, "status": f"{type(e).__name__}"}


def compute_gates(case):
    provs = case["providers"]
    turns = {p: (e.get("transcript") or {}).get("num_turns", 0) for p, e in provs.items()}
    firsts = {}
    for p, e in provs.items():
        t = (e.get("transcript") or {}).get("turns") or []
        firsts[p] = (t[0].get("user", "").strip().lower()[:200] if t else "")
    min_ok = len(turns) == 3 and all(v >= 15 for v in turns.values())
    same_first = len({v for v in firsts.values() if v}) <= 1
    return {
        "min_length": {"pass": bool(min_ok), "turns": turns,
                       "detail": "real user turns per provider; need >=15 each"},
        "shared_prompt": {"pass": bool(same_first),
                          "detail": "first user turn identical across providers"},
        "same_uploads": {"pass": None, "detail": "uploads not compared in active ingest"},
    }


def render_txt(tid, prov, url, turns):
    lines = [f"# {tid} — {prov}", f"# {url}", f"# {len(turns)} turns", ""]
    for i, t in enumerate(turns, 1):
        lines += [f"===== turn {i} =====", "user:", t.get("user", "") or "(no text)", "",
                  "response:", t.get("response", "") or "(no response)", ""]
    return "\n".join(lines).rstrip() + "\n"


def provider_slots(group, idx):
    """provider_1/2/3 from 'provider #' (fallback: row order)."""
    slots = {}
    def g(row, col): return row[idx[col]].strip() if col in idx else ""
    for row in group:
        prov = g(row, "provider")
        num = g(row, "provider #")
        try: n = int(float(num))
        except: n = None
        if n in (1, 2, 3): slots[n] = prov
    if len(slots) != 3:  # fallback to row order
        slots = {i + 1: g(group[i], "provider") for i in range(min(3, len(group)))}
    return slots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--tasks", help="comma-separated task ids")
    ap.add_argument("--tasks-file", help="JSON array of task ids")
    ap.add_argument("--txt-dir", default=os.path.join(HERE, "transcripts"))
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--include-bot", action="store_true", help="also ingest scale@scale.com attempts")
    ap.add_argument("--levels", default="", help="comma-separated review levels to keep (e.g. 'L1,L10'); empty = all")
    a = ap.parse_args()

    BOT_ATTEMPTERS = set() if a.include_bot else {"scale@scale.com"}  # scale-bot attempts — normally skipped
    rows = list(csv.reader(open(a.csv, newline="", encoding="utf-8")))
    hi = 0  # tolerate a leading export/metadata row: header = first row containing 'task id'
    for i, r in enumerate(rows[:6]):
        if any((c or "").strip().lower() == "task id" for c in r): hi = i; break
    hdr = [c.strip() for c in rows[hi]]; idx = {h: i for i, h in enumerate(hdr)}
    def g(row, col): return row[idx[col]].strip() if col in idx and idx[col] < len(row) else ""

    LEVELS = {x.strip().upper() for x in (a.levels or "").split(",") if x.strip()}  # e.g. {"L1","L10"}
    groups = defaultdict(list)
    for r in rows[hi + 1:]:
        if not g(r, "task id"): continue
        if g(r, "submitted by").lower() in BOT_ATTEMPTERS: continue  # skip scale-bot
        if LEVELS and g(r, "level").strip().upper() not in LEVELS: continue  # keep only requested review levels
        groups[g(r, "task id")].append(r)

    if a.tasks_file:
        targets = json.load(open(a.tasks_file))
    elif a.tasks:
        targets = [t.strip() for t in a.tasks.split(",") if t.strip()]
    else:
        targets = list(groups)
    targets = [t for t in targets if t in groups]

    os.makedirs(WORKSPACE, exist_ok=True); os.makedirs(a.txt_dir, exist_ok=True); os.makedirs(a.run, exist_ok=True)
    turns_summary = OrderedDict(); sheet_rows = []
    b = Browser(headless=True)
    try:
        for ti, tid in enumerate(targets, 1):
            group = groups[tid]
            by_prov = {g(row, "provider").lower(): row for row in group}
            first = group[0]
            case = {"task_id": tid, "shared": {}, "providers": {}}
            for c in SHARED_COLS:
                case["shared"][c] = g(first, c)
            case["shared"]["country"] = g(first, "country")  # blank if the CSV has no country col yet
            # reorder shared to match the canonical key order (country after task category)
            case["shared"] = {k: case["shared"].get(k, "") for k in
                              ["persona", "modality", "tier", "task category", "country",
                               "prompt", "user scenario", "desired end state", "trajectory plan"]}

            entry = {"urls": {}, "turns": {}, "valid": {}, "status": {}, "detail": {}}
            for prov in PROVIDERS:
                row = by_prov.get(prov)
                raw = g(row, "session link") if row is not None else ""
                url = clean(raw)
                entry["urls"][prov] = url or raw
                res = classify(raw, b.ctx)
                st = res["status"]; entry["status"][prov] = st
                entry["detail"][prov] = res.get("detail", ""); entry["valid"][prov] = (st == "WORKING")
                turns = []
                if res.get("turns", 0) and url:
                    tr = extract_url(b.ctx, url); turns = tr.get("turns", [])
                    open(os.path.join(a.txt_dir, f"{g(row,'attempt id')}_{prov}.txt"), "w").write(render_txt(tid, prov, url, turns))
                    note = tr.get("note", "")
                else:
                    note = res.get("detail", "")
                entry["turns"][prov] = len(turns)
                if row is None:
                    continue
                # build the case-file provider entry (active schema)
                pe = {"provider": prov, "model_used": g(row, "model used") or g(row, "model used (other)"),
                      "transcript": {"turns": turns, "num_turns": len(turns), "note": note},
                      "links": {}, "ratings": {}, "had_to_change": g(row, "had to change"),
                      "other_thoughts": g(row, "other thoughts"), "artifacts": {}}
                pe["links"]["session_link"] = [{"url": u, "status": 200 if st == "WORKING" else st} for u in split_links(g(row, "session link"))]
                pe["links"]["session_pdf"] = [{"url": u, "status": 200} for u in split_links(g(row, "session pdf"))]
                uploads = parse_uploads(g(row, "produced artifacts"))   # new: JSON-array aware (name+url+mime+bytes)
                pe["links"]["session_artifacts"] = [{"url": a["url"], "name": a["name"],
                                                     "mimeType": a["mimeType"], "bytes": a["bytes"], "status": 200} for a in uploads]
                if uploads and not a.no_download:
                    dest = os.path.join(ART_DIR, tid, prov)
                    pe["artifacts"]["session_artifacts"] = [{**download(a["url"], dest), "name": a["name"]} for a in uploads]
                else:
                    pe["artifacts"]["session_artifacts"] = [{"url": a["url"], "name": a["name"], "saved": None, "status": "skipped"} for a in uploads]
                for col, key in RATING_COLS.items():
                    pe["ratings"][key] = {"score": g(row, col), "justification": g(row, col + " just")}
                case["providers"][prov] = pe

            entry["all_valid"] = all(entry["valid"].values())
            turns_summary[tid] = entry
            case["gates"] = compute_gates(case)
            json.dump(case, open(os.path.join(WORKSPACE, f"task_{tid}.json"), "w"), indent=2, ensure_ascii=False)

            slots = provider_slots(group, idx)
            sheet_rows.append({
                "task id": tid, "attempt id": g(first, "attempt id"), "attempter": g(first, "submitted by"),
                "country": g(first, "country"), "submitted (pt)": g(first, "submitted (pt)"), "status": g(first, "status"),
                "chatgpt session link": g(by_prov.get("chatgpt", first), "session link") if "chatgpt" in by_prov else "",
                "claude session link": g(by_prov.get("claude", first), "session link") if "claude" in by_prov else "",
                "gemini session link": g(by_prov.get("gemini", first), "session link") if "gemini" in by_prov else "",
                "taxonomy_type": g(first, "taxonomy"), "review_level": g(first, "level"),
                "provider_1": slots.get(1, ""), "provider_2": slots.get(2, ""), "provider_3": slots.get(3, ""),
            })
            v = entry["valid"]
            print(f"[{ti}/{len(targets)}] {tid[-6:]}: cg={v['chatgpt']}({entry['turns']['chatgpt']}) "
                  f"cl={v['claude']}({entry['turns']['claude']}) ge={v['gemini']}({entry['turns']['gemini']}) all_valid={entry['all_valid']}")
    finally:
        b.close()

    json.dump(turns_summary, open(os.path.join(a.run, "turns_summary.json"), "w"), indent=2, ensure_ascii=False)
    json.dump(sheet_rows, open(os.path.join(a.run, "sheet_tasks.json"), "w"), indent=2, ensure_ascii=False)
    nvalid = sum(1 for e in turns_summary.values() if e["all_valid"])
    print(f"\ningested {len(turns_summary)} tasks — {nvalid} all-links-valid — "
          f"case files in workspace/, .txt (by attempt id) in {os.path.relpath(a.txt_dir, HERE)}/")


if __name__ == "__main__":
    main()
