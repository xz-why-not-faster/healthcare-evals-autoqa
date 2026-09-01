#!/usr/bin/env python3
"""
link_check.py — LIVE re-validation of session share links (NOT the stale ingest-time status).

Why this exists: a link's HTTP status at ingest is meaningless later — shares get deleted, unshared,
or expire (e.g. f2f8's ChatGPT/Claude shares were deleted after ingest but still returned HTTP 200).
This actually re-loads each session link NOW and classifies its real current state.

Classification per session link:
  WORKING          — the share loads and a real conversation is present (turns > 0)
  DELETED          — the page explicitly says the conversation was deleted / not found
  NOT_PUBLIC       — redirects to sign-in, or a Gemini private /app URL (not a public share)
  EMPTY_OR_BLOCKED — loads (HTTP 200) but no conversation data extracted (empty share OR a bot-block)
  DEAD             — non-2xx HTTP
  NO_URL           — the cell has no usable URL

Writes each result into the case file at providers[model].transcript.live_status, and a summary CSV
at reports/live_link_status.csv. report.broken_links() prefers live_status when present.

    python link_check.py --all           # re-check every task's session links
    python link_check.py --task <id>
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "turn_counter_share"))
from transcript_exporter import Browser, extract_url  # noqa: E402

WS = os.path.join(HERE, "workspace")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
DELETED_MARKERS = ("conversation has been deleted", "conversation not found", "no longer available",
                   "isn't available", "chat not found", "this share link is no longer")
SIGNIN_MARKERS = ("log in to", "sign in", "sign up for free", "continue with google")


def clean(u):
    m = re.match(r"(https?://\S+)", (u or "").strip())
    return m.group(1) if m else ""


def _curl(u):
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, r.read(600000).decode("utf-8", "ignore")


def classify(url, ctx):
    u = clean(url)
    if not u:
        return {"status": "NO_URL", "turns": 0, "detail": (url or "")[:60]}
    # Ground truth for "is there a conversation": actually load & extract it now.
    try:
        res = extract_url(ctx, u)
    except Exception as e:
        res = {"turns": [], "note": f"error:{type(e).__name__}"}
    n = len(res.get("turns", []))
    if n > 0:
        return {"status": "WORKING", "turns": n, "detail": ""}
    # 0 turns / not-public — curl the page to tell DELETED vs sign-in vs bot-block.
    try:
        code, html = _curl(u)
    except urllib.error.HTTPError as e:
        return {"status": "DEAD", "turns": 0, "detail": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "DEAD", "turns": 0, "detail": f"{type(e).__name__}"}
    low = html.lower()
    if any(m in low for m in DELETED_MARKERS):
        return {"status": "DELETED", "turns": 0, "detail": "page reports conversation deleted / not found"}
    if "gemini.google.com/app" in u:
        return {"status": "NOT_PUBLIC", "turns": 0, "detail": "private /app URL, not a public share"}
    if any(s in low for s in SIGNIN_MARKERS) and "linear_conversation" not in html:
        return {"status": "NOT_PUBLIC", "turns": 0, "detail": "redirects to sign-in"}
    if "linear_conversation" in html:
        return {"status": "WORKING", "turns": 0, "detail": "conversation data present but scraper got 0 turns (bot-block; link OK)"}
    return {"status": "EMPTY_OR_BLOCKED", "turns": 0,
            "detail": f"HTTP {code}, {len(html)}B, no conversation data (empty share or bot-block)"}


def run(task_ids):
    b = Browser(headless=True)
    rows = []
    try:
        for tid in task_ids:
            path = os.path.join(WS, f"task_{tid}.json")
            if not os.path.exists(path):
                print(f"!! {tid} not found"); continue
            c = json.load(open(path))
            for prov in ("chatgpt", "claude", "gemini"):
                e = c["providers"].get(prov, {})
                t = e.get("transcript") or {}
                url = t.get("url", "")
                r = classify(url, b.ctx)
                t["live_status"] = r
                e["transcript"] = t
                rows.append({"task id": tid, "provider": prov, "status": r["status"],
                             "turns_now": r["turns"], "detail": r["detail"], "url": clean(url)})
                print(f"  {tid[-6:]} {prov:8} -> {r['status']:16} {r['detail'][:60]}")
            json.dump(c, open(path, "w"), indent=2)
    finally:
        b.close()
    out = os.path.join(HERE, "reports", "live_link_status.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["task id", "provider", "status", "turns_now", "detail", "url"])
        w.writeheader(); w.writerows(rows)
    bad = [r for r in rows if r["status"] not in ("WORKING",)]
    print(f"\nwrote {out} ({len(rows)} links) — {len(bad)} NOT working:")
    for r in bad:
        print(f"  {r['task id'][-6:]} {r['provider']}: {r['status']} — {r['detail'][:70]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task")
    p.add_argument("--all", action="store_true")
    a = p.parse_args()
    if a.all:
        ids = sorted(json.load(open(f))["task_id"] for f in glob.glob(f"{WS}/task_*.json"))
    elif a.task:
        ids = [a.task]
    else:
        p.error("give --task or --all")
    run(ids)


if __name__ == "__main__":
    main()
