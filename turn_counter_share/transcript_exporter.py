#!/usr/bin/env python3
"""
transcript_exporter.py — Export the FULL text of a Claude / ChatGPT / Gemini
share link as a turn-by-turn transcript.

Same browser trick as turn_counter.py (share pages are JS-rendered behind bot
protection, so we drive a real Chrome via Playwright), but instead of just
counting user turns this pulls every user message and the assistant's visible
reply and writes them out as:

    ===== turn 1 =====
    user:
    <what the user said>

    response:
    <what the assistant replied>

    ===== turn 2 =====
    ...

Where the text comes from (authoritative data, not DOM scraping, except Gemini):
  • Claude   — share API `chat_messages`; text blocks of each human/assistant msg.
  • ChatGPT  — embedded `linear_conversation`; user messages + the assistant
               `content_type == "text"` replies (skips thoughts / reasoning /
               tool calls / the custom-instructions pseudo-turn).
  • Gemini   — rendered <user-query> paired 1:1 with <response-container>.

Usage
-----
    python transcript_exporter.py --url https://claude.ai/share/XXXX
    python transcript_exporter.py --urls links.txt          # one URL per line
    python transcript_exporter.py --url ... --out convo.txt  # write to one file
    python transcript_exporter.py --urls links.txt --out-dir transcripts/

With --urls (and no --out), each conversation is written to its own file named
<platform>_<id>.txt in --out-dir (default: current directory). --stdout also
prints to the terminal. --headless / TURN_HEADLESS=1 hides the browser window.
"""
import argparse
import json
import os
import re
import sys

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SIGNIN_MARKERS = ("sign in", "log in to", "continue with google", "sign up for free")
CGPT_NON_TURN_PREFIXES = ("original custom instructions",)


class Browser:
    """Thin wrapper around a persistent Playwright context (mirrors turn_counter.py)."""
    def __init__(self, headless=None):
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
# Each extractor returns {"turns": [{"user": str, "response": str}, ...],
#                         "note": str}  — note is "" on success.
# ---------------------------------------------------------------------------
def _find_chat_messages(obj):
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


def _claude_text(msg):
    """Join the visible text blocks of a Claude message; note attachments."""
    parts = []
    content = msg.get("content")
    if isinstance(content, list):
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text" and blk.get("text"):
                parts.append(blk["text"])
    if not parts and msg.get("text"):
        parts.append(msg["text"])
    text = "\n\n".join(parts).strip()
    names = []
    for f in (msg.get("attachments") or []):
        n = f.get("file_name") or f.get("name") if isinstance(f, dict) else None
        if n:
            names.append(n)
    for f in (msg.get("files") or []):
        n = (f.get("file_name") or f.get("file_kind") or f.get("name")) if isinstance(f, dict) else None
        if n:
            names.append(n)
    if names:
        tag = "[attached: " + ", ".join(names) + "]"
        text = (text + "\n" + tag).strip() if text else tag
    return text


def extract_claude(ctx, url):
    page = ctx.new_page()
    captured = []

    def _grab(r):
        try:
            if "application/json" in r.headers.get("content-type", ""):
                captured.append(r.json())
        except Exception:
            pass  # response body gone (page closing) — ignore

    page.on("response", _grab)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        page.close()
        return {"turns": [], "note": f"error:{e}"}
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
        return {"turns": [], "note": "not public"}
    msgs = sorted(msgs, key=lambda m: m.get("index", 0))
    turns = []
    for m in msgs:
        sender = m.get("sender") or m.get("role")
        txt = _claude_text(m)
        if sender == "human":
            turns.append({"user": txt, "response": ""})
        elif sender == "assistant":
            if turns and not turns[-1]["response"]:
                turns[-1]["response"] = txt
            elif turns:
                turns[-1]["response"] += ("\n\n" + txt)
            else:
                turns.append({"user": "", "response": txt})
    return {"turns": turns, "note": ""}


def _cgpt_decoder(arr):
    def dec(ref, depth=0):
        if not isinstance(ref, int) or ref < 0 or ref >= len(arr) or depth > 12:
            return ref if depth <= 12 else None
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
    return dec


def _strip_cgpt_citations(text):
    """Remove ChatGPT's inline citation tokens (wrapped in U+E200..U+E201)
    plus any other stray private-use-area markers, e.g. 'fileciteturn0file0L4-L8'."""
    text = re.sub("\ue200.*?\ue201", "", text, flags=re.S)   # full citation spans
    text = re.sub("[\ue000-\uf8ff]", "", text)               # any leftover PUA chars
    return text


def _cgpt_parts_text(content):
    """Extract only the string parts (drops image/multimodal pointers)."""
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return _strip_cgpt_citations("\n".join(p for p in parts if isinstance(p, str))).strip()


def extract_chatgpt(ctx, url):
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        page.close()
        return {"turns": [], "note": f"error:{e}"}
    arr = None
    for _ in range(15):
        page.wait_for_timeout(700)
        html = page.content()
        chunks = re.findall(r'enqueue\("((?:[^"\\]|\\.)*)"\)', html)
        target = next((c for c in chunks if "linear_conversation" in c), None)
        if target is not None:
            arr = json.loads(json.loads('"' + target + '"'))
            break
    if arr is None:
        body = page.evaluate("()=>document.body.innerText").lower()[:400]
        page.close()
        return {"turns": [], "note": "not public" if any(s in body for s in SIGNIN_MARKERS) else "no data"}
    page.close()
    dec = _cgpt_decoder(arr)
    refs = arr[arr.index("linear_conversation") + 1]
    turns = []
    for r in refs:
        node = dec(r)
        msg = node.get("message") if isinstance(node, dict) else None
        if not isinstance(msg, dict):
            continue
        author = msg.get("author")
        role = author.get("role") if isinstance(author, dict) else None
        content = msg.get("content")
        ctype = content.get("content_type") if isinstance(content, dict) else None
        if role == "user" and ctype in ("text", "multimodal_text"):
            txt = _cgpt_parts_text(content)
            if txt.lower().startswith(CGPT_NON_TURN_PREFIXES):
                continue  # custom-instructions pseudo-turn
            turns.append({"user": txt, "response": ""})
        elif role == "assistant" and ctype == "text" and msg.get("recipient", "all") == "all":
            txt = _cgpt_parts_text(content)
            if not txt:
                continue
            if turns:
                turns[-1]["response"] += (("\n\n" + txt) if turns[-1]["response"] else txt)
            else:
                turns.append({"user": "", "response": txt})
    return {"turns": turns, "note": ""}


def extract_gemini(ctx, url):
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        page.close()
        return {"turns": [], "note": f"error:{e}"}
    n = 0
    for _ in range(18):
        page.wait_for_timeout(800)
        try:
            n = page.evaluate("()=>document.querySelectorAll('user-query').length")
        except Exception:
            n = 0
        if n > 0:
            page.mouse.wheel(0, 12000)
            page.wait_for_timeout(600)
            got = page.evaluate("()=>document.querySelectorAll('response-container').length")
            if got >= n:
                break
    if n == 0:
        page.close()
        return {"turns": [], "note": "not public"}
    pairs = page.evaluate("""()=>{
      const clean = s => (s||'').replace(/\\r/g,'').trim();
      const uq=[...document.querySelectorAll('user-query')];
      const rc=[...document.querySelectorAll('response-container')];
      const out=[];
      for(let i=0;i<uq.length;i++){
        // Prefer the query-text node (excludes the file carousel); fall back to full text.
        const qt=uq[i].querySelector('.query-text');
        let u = clean((qt?qt.innerText:uq[i].innerText)).replace(/^You said\\s*/i,'').trim();
        // Capture attached file names separately.
        const files=[...uq[i].querySelectorAll('user-query-file-preview')]
          .map(e=>clean(e.innerText).replace(/\\n+/g,' ')).filter(Boolean);
        if(files.length) u=(u? u+'\\n':'')+'[attached: '+files.join(', ')+']';
        // Response: drop bare source-chip lines that are just 'PDF'/'Sources'.
        let r='';
        if(rc[i]){
          r=clean(rc[i].innerText).split('\\n')
            .filter(ln=>!/^(PDF|Sources?)$/i.test(ln.trim()))
            .join('\\n').replace(/\\n{3,}/g,'\\n\\n').trim();
        }
        out.push({user:u, response:r});
      }
      return out;
    }""")
    page.close()
    turns = [{"user": p.get("user", ""), "response": p.get("response", "")} for p in pairs]
    return {"turns": turns, "note": "" if all(t["response"] for t in turns) else "some responses empty"}


def extract_url(ctx, url):
    if not url:
        return {"turns": [], "note": "no link"}
    if "claude.ai/share" in url:
        return extract_claude(ctx, url)
    if "chatgpt.com/share" in url or "chat.openai.com/share" in url:
        return extract_chatgpt(ctx, url)
    if "gemini.google" in url or "g.co/gemini" in url:
        return extract_gemini(ctx, url)
    return {"turns": [], "note": "unknown platform"}


# ---------------------------------------------------------------------------
# Formatting / output
# ---------------------------------------------------------------------------
def platform_of(url):
    if "claude.ai" in url:
        return "claude"
    if "chatgpt.com" in url or "chat.openai.com" in url:
        return "chatgpt"
    if "gemini.google" in url or "g.co/gemini" in url:
        return "gemini"
    return "unknown"


def id_of(url):
    m = re.search(r"/([A-Za-z0-9_\-]+)/?$", url.strip())
    return m.group(1) if m else "convo"


def dedupe_turns(turns):
    """Collapse consecutive turns whose user text is identical (ignoring
    whitespace/case) — e.g. ChatGPT's regenerated/branched answers that keep
    the same question twice. Keeps the LAST occurrence (the final branch).
    Returns (deduped_turns, num_removed)."""
    def norm(s):
        return re.sub(r"\s+", " ", (s or "")).strip().lower()
    out = []
    for t in turns:
        if out and norm(t["user"]) == norm(out[-1]["user"]) and t["user"].strip():
            out[-1] = t  # supersede the previous copy with this (later) one
        else:
            out.append(t)
    return out, len(turns) - len(out)


def render(url, result):
    plat = platform_of(url)
    lines = [f"# {plat} transcript", f"# {url}"]
    if result["note"]:
        lines.append(f"# note: {result['note']}")
    lines.append(f"# {len(result['turns'])} turns")
    lines.append("")
    for i, t in enumerate(result["turns"], 1):
        lines.append(f"===== turn {i} =====")
        lines.append("user:")
        lines.append(t["user"] if t["user"] else "(no text)")
        lines.append("")
        lines.append("response:")
        lines.append(t["response"] if t["response"] else "(no response captured)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    p = argparse.ArgumentParser(description="Export full turn-by-turn transcripts from share links.")
    p.add_argument("--url", help="A single share URL.")
    p.add_argument("--urls", help="Path to a text file with one share URL per line.")
    p.add_argument("--out", help="Write to this single file (only valid with one URL).")
    p.add_argument("--out-dir", default=".", help="Directory for per-URL files (default: cwd).")
    p.add_argument("--stdout", action="store_true", help="Also print transcripts to the terminal.")
    p.add_argument("--dedupe", action="store_true",
                   help="Collapse consecutive turns with an identical user message (keeps the "
                        "last), e.g. ChatGPT regenerated/branched answers.")
    p.add_argument("--headless", action="store_true",
                   help="Run the browser off-screen (also settable via TURN_HEADLESS=1).")
    a = p.parse_args()

    urls = []
    if a.url:
        urls = [a.url.strip()]
    elif a.urls:
        urls = [ln.strip() for ln in open(a.urls) if ln.strip()]
    else:
        p.error("Provide --url or --urls.")

    if a.out and len(urls) != 1:
        p.error("--out only works with a single --url; use --out-dir for multiple.")

    b = Browser(headless=a.headless)
    try:
        for u in urls:
            result = extract_url(b.ctx, u)
            if a.dedupe and result["turns"]:
                result["turns"], removed = dedupe_turns(result["turns"])
                if removed:
                    note = f"deduped {removed} duplicate turn(s)"
                    result["note"] = (result["note"] + "; " + note) if result["note"] else note
            text = render(u, result)
            if a.out:
                path = a.out
            else:
                os.makedirs(a.out_dir, exist_ok=True)
                path = os.path.join(a.out_dir, f"{platform_of(u)}_{id_of(u)}.txt")
            with open(path, "w") as f:
                f.write(text)
            status = result["note"] or f"{len(result['turns'])} turns"
            print(f"[{platform_of(u)}] {u}  ->  {path}  ({status})")
            if a.stdout:
                print("\n" + text + "\n" + "-" * 70)
    finally:
        b.close()


if __name__ == "__main__":
    main()
