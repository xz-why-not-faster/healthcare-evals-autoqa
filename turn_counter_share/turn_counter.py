#!/usr/bin/env python3
"""
turn_counter.py — Count conversation turns in Claude / ChatGPT / Gemini share links.

Why this exists
---------------
Share pages for all three assistants are JavaScript-rendered and sit behind bot
protection, so `curl` / plain HTTP fetches only get an empty shell. This tool
drives a REAL browser (Playwright + your installed Chrome) so the page's JS runs
and any bot challenge clears the way it does for a human.

It then counts *user turns* from the most authoritative source available for each
platform (NOT by scraping the visible DOM, which under-counts hidden turns):

  • Claude   — the share API's `chat_messages` array; counts sender == "human".
  • ChatGPT  — the conversation embedded in the page's turbo-stream payload
               (`linear_conversation`); counts author.role == "user", EXCLUDING
               the custom-instructions pseudo-turn ("Original custom instructions
               no longer available") and system/tool messages.
  • Gemini   — rendered <user-query> elements that contain text (Gemini has no
               public data blob; this DOM count matched Claude+ChatGPT on 200+
               cross-checked rows).

Gotchas it handles
------------------
  • ChatGPT stores custom instructions as a fake "user" message — counting it
    inflates every affected conversation by 1. This tool excludes it.
  • ChatGPT hides image-generation turns from the visible DOM when logged out;
    the embedded data still has them, so we parse that instead.
  • Deleted / unshared links redirect to a sign-in page → reported as "not public".

Two ways to use it
------------------
1) Ad-hoc, no Google auth needed — count a URL or a file of URLs, print a table:
       python turn_counter.py --url https://claude.ai/share/....
       python turn_counter.py --urls links.txt          # one URL per line

2) Google Sheet mode — read link columns, (optionally) verify vs a "min turns"
   column, write counts + a 3-way match verdict back to output columns:
       python turn_counter.py --sheet <SPREADSHEET_ID> --tab "L12 Audits" \
           --gemini-col Q --chatgpt-col R --claude-col S \
           --constraint-col N \
           --verify-col AN --count-col AO --match-col AP \
           --first-row 2 --last-row 247
   Add --dry-run to preview without writing. Results are cached to a local
   .turn_cache.jsonl so re-runs / crashes resume instead of re-fetching.

Setup
-----
   pip install playwright google-api-python-client google-auth-httplib2 \
               google-auth-oauthlib
   python -m playwright install chromium      # or rely on installed Chrome
   # Google Sheet mode also needs an OAuth client: put credentials.json in the
   # working dir (Desktop-app OAuth client with the Sheets scope). First run
   # opens a browser to authorize and writes token.json next to it.

A window will open and cycle through the links — that's expected; a real browser
is what clears the bot challenge. ~5-8s per link.
"""
import argparse
import json
import re
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# Browser session
# ---------------------------------------------------------------------------
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SIGNIN_MARKERS = ("sign in", "log in to", "continue with google", "sign up for free")
CGPT_NON_TURN_PREFIXES = ("original custom instructions",)


class Browser:
    """Thin wrapper around a persistent Playwright context."""
    def __init__(self, headless=None):
        import os
        from playwright.sync_api import sync_playwright
        if headless is None:
            headless = os.environ.get("TURN_HEADLESS", "").lower() in ("1", "true", "yes")
        self._pw = sync_playwright().start()
        args = ["--disable-blink-features=AutomationControlled"]
        try:
            self.browser = self._pw.chromium.launch(channel="chrome", headless=headless, args=args)
        except Exception:
            self.browser = self._pw.chromium.launch(headless=headless, args=args)
        self.ctx = self.browser.new_context(
            user_agent=UA, viewport={"width": 1280, "height": 1000}, locale="en-US")
        self.ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

    def close(self):
        try:
            self.browser.close()
        finally:
            self._pw.stop()


# ---------------------------------------------------------------------------
# Per-platform counters — each returns {"n": int|None, "note": str}
# ---------------------------------------------------------------------------
def _find_chat_messages(obj):
    """Recursively locate a chat_messages-like list of {sender|role} dicts."""
    if isinstance(obj, dict):
        for k in ("chat_messages", "messages"):
            v = obj.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict) and \
               any(key in v[0] for key in ("sender", "role")):
                return v
        for v in obj.values():
            r = _find_chat_messages(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_chat_messages(v)
            if r:
                return r
    return None


def count_claude(ctx, url):
    page = ctx.new_page()
    captured = []
    page.on("response", lambda r: captured.append(r.json())
            if "application/json" in r.headers.get("content-type", "") else None)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        page.close()
        return {"n": None, "note": f"error:{e}"}
    msgs = None
    for _ in range(25):
        page.wait_for_timeout(900)
        for data in captured:
            try:
                m = _find_chat_messages(data)
            except Exception:
                m = None
            if m:
                msgs = m
                break
        if msgs:
            break
    page.close()
    if not msgs:
        return {"n": None, "note": "not public"}
    c = Counter((m.get("sender") or m.get("role")) for m in msgs)
    return {"n": c.get("human", 0), "note": ""}


def _parse_chatgpt(html):
    """Return list of user-turn text snippets from the turbo-stream, or None."""
    chunks = re.findall(r'enqueue\("((?:[^"\\]|\\.)*)"\)', html)
    target = next((c for c in chunks if "linear_conversation" in c), None)
    if target is None:
        return None
    arr = json.loads(json.loads('"' + target + '"'))  # JS-string -> str -> JSON array

    def dec(ref, depth=0):
        if not isinstance(ref, int) or ref < 0 or ref >= len(arr) or depth > 10:
            return ref if depth <= 10 else None
        v = arr[ref]
        if isinstance(v, dict):
            out = {}
            for k, vv in v.items():
                kn = int(k[1:]) if k.startswith("_") else k
                key = arr[kn] if isinstance(kn, int) and 0 <= kn < len(arr) else kn
                out[key] = dec(vv, depth + 1)
            return out
        if isinstance(v, list):
            return [dec(x, depth + 1) for x in v]
        return v

    refs = arr[arr.index("linear_conversation") + 1]
    users = []
    for r in refs:
        node = dec(r)
        msg = node.get("message") if isinstance(node, dict) else None
        if isinstance(msg, dict) and isinstance(msg.get("author"), dict) \
                and msg["author"].get("role") == "user":
            content = msg.get("content")
            parts = content.get("parts") if isinstance(content, dict) else None
            txt = parts[0] if isinstance(parts, list) and parts and isinstance(parts[0], str) else ""
            users.append(txt or "")
    return users


def count_chatgpt(ctx, url):
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        page.close()
        return {"n": None, "note": f"error:{e}"}
    users = None
    for _ in range(15):
        page.wait_for_timeout(700)
        users = _parse_chatgpt(page.content())
        if users is not None:
            break
    if users is None:
        body = page.evaluate("()=>document.body.innerText").lower()[:400]
        page.close()
        return {"n": None, "note": "not public" if any(s in body for s in SIGNIN_MARKERS) else "no data"}
    page.close()
    # Keep real turns (incl. empty/multimodal); drop only the custom-instructions pseudo-turn.
    real = [u for u in users if not u.lower().startswith(CGPT_NON_TURN_PREFIXES)]
    return {"n": len(real), "note": ""}


def count_gemini(ctx, url):
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        page.close()
        return {"n": None, "note": f"error:{e}"}
    raw = txt = 0
    stable = 0
    for _ in range(16):
        page.wait_for_timeout(700)
        try:
            d = page.evaluate("""()=>{const qs=document.querySelectorAll('user-query');
              let raw=qs.length,txt=0;
              qs.forEach(e=>{if((e.innerText||'').trim().length>0)txt++;});
              return {raw,txt};}""")
        except Exception:
            d = {"raw": 0, "txt": 0}
        if d["txt"] == txt and txt > 0:
            stable += 1
            if stable >= 2:
                raw = max(raw, d["raw"])
                break
        else:
            stable = 0
        raw = max(raw, d["raw"])
        txt = max(txt, d["txt"])
        if txt > 0:
            page.mouse.wheel(0, 6000)
    page.close()
    if raw == 0:
        return {"n": None, "note": "not public"}
    return {"n": txt, "note": "" if raw == txt else f"raw{raw}/text{txt}"}


def count_url(ctx, url):
    """Dispatch a single URL to the right counter based on its host."""
    if not url:
        return {"n": None, "note": "no link"}
    if "claude.ai/share" in url:
        return count_claude(ctx, url)
    if "chatgpt.com/share" in url or "chat.openai.com/share" in url:
        return count_chatgpt(ctx, url)
    if "gemini.google" in url or "g.co/gemini" in url:
        return count_gemini(ctx, url)
    return {"n": None, "note": "unknown platform"}


# ---------------------------------------------------------------------------
# Constraint check (e.g. "6+", "4-5", "2-3", "1")
# ---------------------------------------------------------------------------
def constraint_ok(turns, con):
    con = (con or "").strip()
    m = re.match(r"^(\d+)\+$", con)
    if m:
        return turns >= int(m.group(1)), f"{m.group(1)}+"
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", con)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return lo <= turns <= hi, f"{lo}-{hi}"
    m = re.match(r"^(\d+)$", con)
    if m:
        n = int(m.group(1))
        return turns == n, f"{n}"
    return None, con


# ---------------------------------------------------------------------------
# Google Sheets helpers (only imported/used in --sheet mode)
# ---------------------------------------------------------------------------
def sheets_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    import os
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                sys.exit("Google Sheet mode needs credentials.json (OAuth desktop client) in this folder.")
            creds = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES).run_local_server(port=0)
        open("token.json", "w").write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def col_values(svc, sid, tab, col, first, last):
    rng = f"'{tab}'!{col}{first}:{col}{last}"
    v = svc.spreadsheets().values().get(spreadsheetId=sid, range=rng).execute().get("values", [])
    out = {}
    for i, cell in enumerate(v):
        out[first + i] = (cell[0].strip() if cell and cell[0] else "")
    return out


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------
def run_urls(urls, headless=None):
    b = Browser(headless=headless)
    try:
        print(f"{'URL':70}  {'TURNS':>6}  NOTE")
        for u in urls:
            r = count_url(b.ctx, u)
            print(f"{u[:70]:70}  {str(r['n']):>6}  {r['note']}")
    finally:
        b.close()


def run_sheet(a):
    import os
    svc = sheets_service()
    cols = {}
    for name, letter in (("gemini", a.gemini_col), ("chatgpt", a.chatgpt_col), ("claude", a.claude_col)):
        if letter:
            cols[name] = col_values(svc, a.sheet, a.tab, letter, a.first_row, a.last_row)
    con = col_values(svc, a.sheet, a.tab, a.constraint_col, a.first_row, a.last_row) if a.constraint_col else {}

    rows = sorted({r for c in cols.values() for r in c})
    cache_path = a.cache or ".turn_cache.jsonl"
    cache = {}
    if os.path.exists(cache_path):
        for line in open(cache_path):
            d = json.loads(line)
            cache[d["row"]] = d

    b = Browser(headless=getattr(a, "headless", None))
    out = open(cache_path, "a")
    try:
        for row in rows:
            if row in cache:
                continue
            rec = {"row": row}
            for name in ("claude", "gemini", "chatgpt"):
                url = cols.get(name, {}).get(row, "")
                rec[name] = count_url(b.ctx, url) if url else {"n": None, "note": "no link"}
            out.write(json.dumps(rec) + "\n")
            out.flush()
            cache[row] = rec
            print(f"row {row}: Cl={rec['claude']['n']} G={rec['gemini']['n']} C={rec['chatgpt']['n']}")
    finally:
        out.close()
        b.close()

    # Build output cells
    data = []
    verify_hdr, count_hdr, match_hdr = "Claude Turns vs Min", "Turns (Claude/Gemini/ChatGPT)", "Turns Match?"
    if a.verify_col:
        data.append({"range": f"'{a.tab}'!{a.verify_col}1", "values": [[verify_hdr]]})
    if a.count_col:
        data.append({"range": f"'{a.tab}'!{a.count_col}1", "values": [[count_hdr]]})
    if a.match_col:
        data.append({"range": f"'{a.tab}'!{a.match_col}1", "values": [[match_hdr]]})

    for row in rows:
        r = cache[row]
        cl, g, c = r["claude"]["n"], r["gemini"]["n"], r["chatgpt"]["n"]
        s = lambda v: str(v) if v is not None else "—"
        if a.verify_col:
            if cl is None:
                note = "⚠️ Claude link not public"
            else:
                ok, label = constraint_ok(cl, con.get(row, ""))
                note = (f"⚠️ {cl} turns — unrecognized constraint '{con.get(row,'')}'" if ok is None
                        else f"✅ {cl} turns — meets {label}" if ok
                        else f"❌ {cl} turns — needs {label}")
            data.append({"range": f"'{a.tab}'!{a.verify_col}{row}", "values": [[note]]})
        if a.count_col:
            data.append({"range": f"'{a.tab}'!{a.count_col}{row}",
                         "values": [[f"Cl {s(cl)} / G {s(g)} / C {s(c)}"]]})
        if a.match_col:
            if any(v is None for v in (cl, g, c)):
                verdict = "⚠️ incomplete (a link not public)"
            elif cl == g == c:
                verdict = f"✅ all match ({cl})"
            else:
                verdict = f"❌ differ ({cl}/{g}/{c})"
            data.append({"range": f"'{a.tab}'!{a.match_col}{row}", "values": [[verdict]]})

    if a.dry_run:
        print(f"\n(dry run) would write {len(data)} cells. Re-run without --dry-run to apply.")
        for d in data[:20]:
            print("  ", d["range"], d["values"][0][0])
        return
    if data:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=a.sheet, body={"valueInputOption": "RAW", "data": data}).execute()
        print(f"\nWrote {len(data)} cells to the sheet.")


def main():
    p = argparse.ArgumentParser(description="Count turns in Claude/ChatGPT/Gemini share links.")
    p.add_argument("--url", help="Count a single share URL and print the result.")
    p.add_argument("--urls", help="Path to a text file with one share URL per line.")
    # Sheet mode
    p.add_argument("--sheet", help="Google Spreadsheet ID.")
    p.add_argument("--tab", help="Worksheet/tab name.")
    p.add_argument("--gemini-col"); p.add_argument("--chatgpt-col"); p.add_argument("--claude-col")
    p.add_argument("--constraint-col", help="Column with the min-turns rule (e.g. '6+', '4-5').")
    p.add_argument("--verify-col", help="Output col for Claude-vs-constraint check.")
    p.add_argument("--count-col", help="Output col for 'Cl x / G y / C z' counts.")
    p.add_argument("--match-col", help="Output col for the 3-way match verdict.")
    p.add_argument("--first-row", type=int, default=2)
    p.add_argument("--last-row", type=int, default=1000)
    p.add_argument("--cache", help="Path to resume cache (default .turn_cache.jsonl).")
    p.add_argument("--dry-run", action="store_true", help="Preview sheet writes without applying.")
    p.add_argument("--headless", action="store_true",
                   help="Run the browser off-screen with no visible window (verified to match "
                        "headed counts exactly; also settable via TURN_HEADLESS=1).")
    a = p.parse_args()

    if a.url:
        run_urls([a.url], headless=a.headless)
    elif a.urls:
        run_urls([ln.strip() for ln in open(a.urls) if ln.strip()], headless=a.headless)
    elif a.sheet:
        if not (a.tab and (a.gemini_col or a.chatgpt_col or a.claude_col)):
            p.error("--sheet mode needs --tab and at least one of --claude-col/--gemini-col/--chatgpt-col")
        run_sheet(a)
    else:
        p.error("Provide --url, --urls, or --sheet ...")


if __name__ == "__main__":
    main()
