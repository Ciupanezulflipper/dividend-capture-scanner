# AI_REVIEW_NOTES.md

Records AI review findings so future sessions do not relitigate settled decisions.

## Thesis Reframe (2026-05-02, joint Claude + ChatGPT-5)
Original "dividend capture" framing was weak — price adjusts around ex-date.
Reframed as: **Dividend Quality Pullback Scanner**
- Ex-dividend date = timing context / catalyst filter
- RSI oversold + price above 200D MA = actual signal condition
- Alerts = candidate research prompts, not buy commands

## Claude — Agreed Decisions
- One canonical filename: `dividend_scanner.py`
- Empty private GitHub repo before first push
- Never commit `.env` — `.env.example` only
- Dedup key: `ticker|ex_date` (not ticker alone — quarterly dividends recur)
- Pure-pandas RSI fallback required
- yfinance calendar → info dict cascade for ex-date discovery
- `CRON_TZ=America/New_York` (not fixed UTC)
- v1 = scanner/alerter only, no execution
- Data quality validation before UI polish
- Sparse signals are a feature, not a bug

## ChatGPT-5 — Flagged Before Implementation
- `requirements.txt` must not contain uncommented prose
- PyPI name `pandas-ta` (hyphen) != Python import `pandas_ta` (underscore)
- `rich` required if dashboard uses Rich console
- HTML parser dependencies required for `pandas.read_html`
- yfinance ex-date coverage is not institutional-grade
- Fixed UTC cron wrong during daylight saving
- Thesis reframe: ex-date as context, not as the edge

## Issues Found and Fixed During Termux Smoke Testing
| Issue | Fix |
|---|---|
| lxml build failure on Termux | Removed from core requirements; optional only |
| pandas-ta blocks startup | Removed from core; optional only; pure-pandas fallback |
| pandas.read_html defaulted to lxml | `flavor="html5lib"` added |
| Wikipedia HTTP 403 | `requests.get` with `User-Agent` header |
| pandas FutureWarning on literal HTML | `StringIO(response.text)` wrapper |

## Post-Commit Validation Results (2026-05-03)

### Telegram Setup — DONE
- Bot: @DividendQualityBot
- Token verified via getMe: PASS
- Chat ID extracted via getUpdates: PASS
- sendMessage test delivered: PASS
- .env ignored by git: PASS
- No secrets committed: PASS

### Weekend Guard — PASS
Running without `--force-weekend` on a weekend exits cleanly with the correct message.
Expected and correct behaviour.

### Forced-Weekend Limited Run — PASS
`./run_bot.sh --limit 10 --show-all --force-weekend`
- 503 tickers fetched from Wikipedia (confirmed universe loads correctly)
- 10 tickers scanned
- 0 signals (correct — RSI/MA/ex-date criteria not met)
- history.json created with empty state (expected on first live run)
- history.json ignored by git (confirmed)
- git status clean

### Stale Ex-Date Data — PROVEN, Not Hypothetical
Log evidence from 10-ticker run:
- ADBE: returned ex_date 2005-03-24 (21 years stale)
- AMD: returned ex_date 1995-04-27 (31 years stale)
yfinance stale ex-date coverage is a confirmed data-quality issue.
Full scan audit will quantify the failure rate across all 500 tickers.

### Signal Sparsity — Expected and Correct
RSI < 38 + price above 200D MA + ex-date within 21 days is sparse.
0 signals on a 10-ticker run is expected. Do not widen threshold.

### This Is a Hypothesis-Testing Tool
Performance must be measured vs SPY over 1/3/5/10/20 trading days post-signal
before any conclusions are drawn.

## Open Items
| Item | Priority | Target |
|---|---|---|
| Full 500-ticker scan + reason-count audit | HIGH | v1.1 next |
| CSV export | MEDIUM | v1.1 |
| Post-signal tracking skeleton | MEDIUM | v1.1 |
| NYSE holiday guard | LOW | after audit |
| Secondary ex-date source | LOW | after audit |
| Ex-date revision / dedup TTL | LOW | v1.2 |
| Dividend quality filters | LOW | v1.2 |
| Threading / scan speed | LOWEST | after reliability proven |
| Dashboard / UI polish | LOWEST | after data quality confirmed |
| Repo rename | DEFERRED | conscious tech debt |
