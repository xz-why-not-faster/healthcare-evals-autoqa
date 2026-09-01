# turn_counter

Count conversation **turns** in Claude / ChatGPT / Gemini share links, straight
from a local Claude Code (or plain Python) session. Built for QMA/QMO turn-match
checks: verify a Claude conversation meets a min-turn rule, compare turn counts
across all three assistants, and flag mismatches.

## Why a browser is required
Share pages are JavaScript-rendered and sit behind bot protection — `curl` and
plain HTTP only see an empty shell. This tool drives your **real installed
Chrome** via Playwright, so the page's JS runs and the bot challenge clears the
way it does for a person. A window opens and cycles through the links (~5–8s
each). That's expected.

### Headless mode (no visible window)
Pass `--headless` (or set `TURN_HEADLESS=1`) to run with no window on screen, so
it doesn't interrupt other work. Verified against 36 known-good links (Claude /
ChatGPT / Gemini): headless counts matched the headed counts **exactly, 0
mismatches** — including ChatGPT (bot-protected) and Gemini (DOM-based). Same
accuracy, no window. `run_l10_turns.py` reads the same `TURN_HEADLESS=1` env var.

## How turns are counted (authoritative sources, not DOM scraping)
| Platform | Source | Counts |
|----------|--------|--------|
| Claude   | share API `chat_messages` | messages where `sender == "human"` |
| ChatGPT  | embedded `linear_conversation` turbo-stream | `author.role == "user"`, minus the custom-instructions pseudo-turn and system/tool msgs |
| Gemini   | rendered `<user-query>` elements | queries containing text |

Two gotchas it handles automatically:
- **ChatGPT custom instructions** serialize as a fake "user" message
  (*"Original custom instructions no longer available"*) — counting it inflates
  ~10% of conversations by 1. Excluded here.
- **ChatGPT hides image-generation turns** from the logged-out DOM; the embedded
  data still has them, so we parse that instead of scraping.

Deleted/unshared links redirect to a sign-in page and are reported `not public`.

## Install
```bash
pip install playwright google-api-python-client google-auth-httplib2 google-auth-oauthlib
python -m playwright install chromium      # or rely on installed Chrome
```

## Usage

**Ad-hoc (no Google auth):**
```bash
python turn_counter.py --url https://claude.ai/share/XXXX
python turn_counter.py --urls links.txt        # one URL per line, any platform
```

**Google Sheet mode** (reads link columns, writes results back):
```bash
python turn_counter.py --sheet <SPREADSHEET_ID> --tab "L12 Audits" \
    --gemini-col Q --chatgpt-col R --claude-col S \
    --constraint-col N \
    --verify-col AN --count-col AO --match-col AP \
    --first-row 2 --last-row 247
```
- `--verify-col` → `✅ 6 turns — meets 6+` (Claude count vs the `--constraint-col`
  rule; understands `6+`, `4-5`, `2-3`, `1`).
- `--count-col`  → `Cl 6 / G 6 / C 6`.
- `--match-col`  → `✅ all match (6)` / `❌ differ (6/6/7)` / `⚠️ incomplete`.
- Any output col you omit is simply not written. Only the columns you name are
  touched — nothing else on the sheet changes.
- Add `--dry-run` to preview writes first.
- Progress is cached to `.turn_cache.jsonl`; re-running resumes instead of
  re-fetching. Delete that file to force a fresh run.

### Google auth (Sheet mode only)
Put a **credentials.json** (OAuth *Desktop app* client, Google Sheets API
enabled) in the working directory. First run opens a browser to authorize and
writes `token.json` beside it. The account needs edit access to the target sheet.

## Persistence & caching (Daily Use Evals L10)

So checks are never repeated and survive sheet refreshes:

- **Caches** (shared, in this folder): `turn_url_cache.jsonl` (keyed by share URL —
  immutable, the primary dedup key) and `turn_attempt_cache.jsonl` (keyed by Attempt
  ID). A URL/Attempt already here is reused, never re-fetched.
- **Hidden `Turns` tab** in the workbook (keyed by Attempt ID) holds the 3 result
  columns. The bound Apps Script (`evals_audit_v9_appscript.js`) **re-joins** them
  into `L10 Audits` (BW/BX/BY) by Attempt ID on every refresh — so turn results
  persist through rebuilds automatically (same pattern as Evals Hints).
- **`run_l10_turns.py`** is the L10 runner: reads L10 Audits, checks only Attempt
  IDs not already cached, appends new results to the `Turns` store + both caches,
  and writes the live BW/BX/BY. Re-run it any time after new rows appear.

The 3 columns: `Claude Turns` = Claude-count-vs-`Min Turns` verdict; `Turns
(Claude/Gemini/ChatGPT)` = counts; `Turns Match SxSxS?` = 3-way match.

## Notes & limitations
- "Turn" = one user message. A trailing "thanks!" with no substantive request
  still counts as a turn — if your convention ignores those, treat ±1 diffs as
  matches.
- Claude & ChatGPT counts are authoritative (from data, not pixels). Gemini is
  DOM-based (no public data blob) but agreed with the other two on 200+
  cross-checked rows.
- Requires a desktop/GUI environment (the browser window must be able to open).
