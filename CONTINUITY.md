# CONTINUITY.md

## Project
Dividend Capture Scanner

## Repository
- Owner: Ciupanezulflipper
- Repo: dividend-capture-scanner
- Visibility: private
- Remote: git@github.com:Ciupanezulflipper/dividend-capture-scanner.git
- Local (Termux): /data/data/com.termux/files/home/dividend-capture-scanner

## Current Verified State — 2026-05-02
| Item | Status |
|---|---|
| GitHub repo created | YES |
| Cloned into Termux | YES |
| GitHub CLI authenticated | YES |
| Git protocol | SSH |
| Control files committed | YES |
| Python scanner committed | YES |
| requirements.txt committed | YES |
| run_bot.sh committed | YES |
| Python syntax check | PASS |
| Bash syntax check | PASS |
| Termux smoke test | PASS |
| **First commit pushed** | **YES — eb5de68** |
| Secrets committed | NO |

## First Commit
- Hash: eb5de68
- Branch: main
- Message: Initial dividend capture scanner
- Files: 10
- First known-good version: YES

## Latest Smoke Test
```
./run_bot.sh --dry-run --limit 10 --show-all
```
Result: PASS
- Scanner started: YES
- S&P 500 fetch: YES
- Limit 10: YES
- Rich dashboard: YES
- Telegram sent: NO (expected — dry-run, no .env)
- history.json created: NO (expected — dry-run)
- Signals found: 0

## Locked Decisions
- Canonical Python file: `dividend_scanner.py`
- v1 scope: scanner/alerter only — no trade execution
- Secrets live in `.env` only — never committed
- `history.json`, logs, `.termux_req_sha256` never committed
- Dedup key: `ticker|ex_date`

## Implementation Files
- `dividend_scanner.py`
- `requirements.txt`
- `run_bot.sh`

## Termux Fixes Applied (committed)
- `lxml` removed from core requirements (build failure on Termux)
- `pandas-ta` removed from core requirements (pure-pandas RSI fallback exists)
- `html5lib` + `beautifulsoup4` are core parser dependencies
- `lxml` and `pandas-ta` attempted optionally in `run_bot.sh`, non-fatal
- Wikipedia fetch uses `requests.get` with `User-Agent`
- `pandas.read_html` uses `flavor="html5lib"` and `StringIO(response.text)`
- `StringIO` import added

## v1.1 Sequencing (locked order)
1. `.env` setup + Telegram delivery test (live alert confirmed)
2. Full 500-ticker scan + log audit (error rate, ex-date coverage quality)
3. NYSE holiday guard
4. CSV export / report mode
5. Secondary ex-dividend validation source

## Signal Frequency Expectation
RSI < 38 AND price > 200D MA AND ex-date within 21 days is a sparse
condition set. Zero signals for days or weeks is normal in a healthy market.
Do NOT loosen RSI threshold out of impatience.

## Known Edge Case (v1.1 review item, not a blocker)
`history.json` dedup key is `ticker|ex_date`. Correct for normal use.
Edge case: if a company revises its ex-date after alert is sent, the old
key persists in history and the revised date may not trigger a new alert.
Track and review in v1.1 or v1.2.
