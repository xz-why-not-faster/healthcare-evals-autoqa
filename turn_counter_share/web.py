#!/usr/bin/env python3
"""
web.py — a tiny local web UI for transcript_exporter.py.

Run it, open the printed URL, paste one or more Claude / ChatGPT / Gemini share
links, and get turn-by-turn transcripts you can read, copy, or download.

    python web.py                 # then open http://127.0.0.1:8765
    python web.py --port 9000
    python web.py --open          # also open the page in your browser

How it works
------------
A plain static .html file can't do this: your browser can't fetch the share
pages cross-origin (CORS) and can't clear the bot protection. So this serves a
small HTML front-end from a local Python process, and does the real extraction
server-side with the same Playwright code as transcript_exporter.py. The browser
Playwright drives always runs headless (no window pops up).

Requests are handled one at a time (a single shared headless browser), which is
plenty for personal use. Nothing leaves your machine except the fetches to the
share links themselves.
"""
import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from transcript_exporter import Browser, dedupe_turns, extract_url, platform_of, render

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Share-link transcript exporter</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 900px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  p.sub { margin: 0 0 20px; opacity: .7; }
  textarea { width: 100%; min-height: 110px; padding: 10px; font: 13px/1.4 ui-monospace, Menlo, monospace;
             border: 1px solid #8884; border-radius: 8px; background: #8881; color: inherit; resize: vertical; }
  .row { display: flex; align-items: center; gap: 14px; margin: 12px 0 20px; flex-wrap: wrap; }
  button { font: inherit; font-weight: 600; padding: 9px 18px; border: 0; border-radius: 8px;
           background: #4f7cff; color: #fff; cursor: pointer; }
  button:disabled { opacity: .5; cursor: default; }
  label.chk { display: flex; align-items: center; gap: 6px; cursor: pointer; }
  #status { opacity: .7; font-size: 13px; }
  .card { border: 1px solid #8884; border-radius: 10px; margin: 16px 0; overflow: hidden; }
  .card > header { display: flex; align-items: center; gap: 10px; padding: 8px 12px;
                   background: #8881; font-size: 13px; }
  .badge { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
           padding: 2px 8px; border-radius: 999px; background: #4f7cff22; color: #4f7cff; }
  .badge.claude { background: #d97a5722; color: #d97a57; }
  .badge.chatgpt { background: #10a37f22; color: #10a37f; }
  .badge.gemini { background: #8a6df022; color: #8a6df0; }
  .card header .grow { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; opacity: .7; }
  .card header button { background: #8883; color: inherit; padding: 5px 12px; font-size: 12px; font-weight: 600; }
  pre { margin: 0; padding: 14px; max-height: 420px; overflow: auto; white-space: pre-wrap;
        word-break: break-word; font: 12.5px/1.5 ui-monospace, Menlo, monospace; }
  .note { color: #c67; font-size: 12px; }
</style>
</head>
<body>
  <h1>Share-link transcript exporter</h1>
  <p class="sub">Paste Claude / ChatGPT / Gemini share links (one per line). Runs a headless browser locally.</p>
  <textarea id="urls" placeholder="https://claude.ai/share/...
https://chatgpt.com/share/...
https://share.gemini.google/..."></textarea>
  <div class="row">
    <button id="go">Export transcripts</button>
    <label class="chk"><input type="checkbox" id="dedupe"> Dedupe repeated turns</label>
    <span id="status"></span>
  </div>
  <div id="results"></div>

<script>
const $ = s => document.querySelector(s);
const esc = s => s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

$('#go').addEventListener('click', async () => {
  const urls = $('#urls').value.split('\\n').map(s => s.trim()).filter(Boolean);
  if (!urls.length) { $('#status').textContent = 'Paste at least one link.'; return; }
  $('#go').disabled = true;
  $('#status').textContent = `Working on ${urls.length} link(s)… (~5-8s each)`;
  $('#results').innerHTML = '';
  try {
    const res = await fetch('/extract', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ urls, dedupe: $('#dedupe').checked })
    });
    const data = await res.json();
    $('#status').textContent = `Done — ${data.length} transcript(s).`;
    for (const r of data) render(r);
  } catch (e) {
    $('#status').textContent = 'Error: ' + e;
  } finally {
    $('#go').disabled = false;
  }
});

function render(r) {
  const card = document.createElement('div');
  card.className = 'card';
  const note = r.note ? ` <span class="note">(${esc(r.note)})</span>` : '';
  card.innerHTML = `
    <header>
      <span class="badge ${r.platform}">${r.platform}</span>
      <span>${r.turns} turns${note}</span>
      <span class="grow">${esc(r.url)}</span>
      <button class="copy">Copy</button>
      <button class="dl">Download</button>
    </header>
    <pre></pre>`;
  card.querySelector('pre').textContent = r.text;
  card.querySelector('.copy').onclick = () => navigator.clipboard.writeText(r.text);
  card.querySelector('.dl').onclick = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([r.text], {type: 'text/plain'}));
    a.download = `${r.platform}_${r.id}.txt`;
    a.click();
  };
  $('#results').appendChild(card);
}
</script>
</body>
</html>
"""


def id_of(url):
    import re
    m = re.search(r"/([A-Za-z0-9_\-]+)/?$", url.strip())
    return m.group(1) if m else "convo"


class Handler(BaseHTTPRequestHandler):
    browser = None  # set in main()

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE)
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/extract":
            self._send(404, "not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send(400, json.dumps({"error": "bad json"}), "application/json")
            return
        urls = [u.strip() for u in req.get("urls", []) if u.strip()]
        dedupe = bool(req.get("dedupe"))
        out = []
        for u in urls:
            try:
                result = extract_url(self.browser.ctx, u)
                if dedupe and result["turns"]:
                    result["turns"], removed = dedupe_turns(result["turns"])
                    if removed:
                        n = f"deduped {removed} duplicate turn(s)"
                        result["note"] = (result["note"] + "; " + n) if result["note"] else n
            except Exception as e:
                result = {"turns": [], "note": f"error:{e}"}
            out.append({
                "url": u,
                "platform": platform_of(u),
                "id": id_of(u),
                "turns": len(result["turns"]),
                "note": result["note"],
                "text": render(u, result),
            })
        self._send(200, json.dumps(out), "application/json")

    def log_message(self, fmt, *args):
        pass  # quiet


def main():
    p = argparse.ArgumentParser(description="Local web UI for the transcript exporter.")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--open", action="store_true", help="Open the page in your browser on start.")
    a = p.parse_args()

    print("Launching headless browser…")
    Handler.browser = Browser(headless=True)
    srv = HTTPServer((a.host, a.port), Handler)
    url = f"http://{a.host}:{a.port}"
    print(f"Ready. Open {url}  (Ctrl-C to stop)")
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
    finally:
        Handler.browser.close()


if __name__ == "__main__":
    main()
