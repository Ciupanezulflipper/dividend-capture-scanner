# AI_REVIEW_NOTES.md

Records AI review findings so future sessions don't relitigate settled decisions.

## Claude — Agreed Decisions
- One canonical filename: `dividend_scanner.py`
- Empty private GitHub repo before first push
- Never commit `.env`
- `.env.example` only in repo
- `.gitignore` before first commit
- Dedup key: `ticker|ex_date` (not ticker alone — quarterly dividends recur)
- Pure-pandas RSI fallback required
- yfinance calendar → info dict cascade for ex-date discovery
- `CRON_TZ=America/New_York` (not fixed UTC — breaks during daylight saving)
- v1 = scanner/alerter only, no execution
- Data quality validation before UI polish

## ChatGPT — Flagged Before Implementation
- `requirements.txt` must not contain uncommented prose
- PyPI name `pandas-ta` (hyphen) != Python import `pandas_ta` (underscore)
- `rich` required if dashboard uses Rich console
- HTML parser dependencies required for `pandas.read_html`
- yfinance ex-date coverage is not institutional-grade
- Fixed UTC cron wrong during daylight saving

## Issues Found and Fixed During Termux Smoke Testing

### Issue 1 — lxml build failure
```
Error: Please make sure the libxml2 and libxslt development packages are installed.
```
Fix: `lxml` removed from `requirements.txt`. Made optional/non-fatal in `run_bot.sh`.

### Issue 2 — pandas-ta blocks startup
Fix: `pandas-ta` removed from `requirements.txt`. Optional only. Pure-pandas fallback active.

### Issue 3 — pandas.read_html defaulted to lxml
```
Missing optional dependency 'lxml'.
```
Fix: `fetch_sp500` calls `pd.read_html(..., flavor="html5lib")`.

### Issue 4 — Wikipedia HTTP 403
Fix: `requests.get` with `User-Agent` header. `response.raise_for_status()` validates.

### Issue 5 — pandas FutureWarning on literal HTML
Fix: `StringIO(response.text)` wrapper. `from io import StringIO` import added.

## Post-Commit Review Notes (Claude, 2026-05-02)

### Signal Sparsity — Expected
RSI < 38 + price above 200D MA + ex-date within 21 days requires three
conditions simultaneously. In a healthy bull market this is rare.
Zero signals for days/weeks does not indicate a broken scanner.
Do not widen RSI threshold to chase signals.

### Dedup Edge Case — Known, Not a Blocker
`history.json` key is `ticker|ex_date`.
Risk: if a company revises its ex-date post-alert, the old key stays in
history and the revised date may be silently missed.
Resolution: document as v1.1/v1.2 review item. Add an ex-date revision
check or TTL-based key expiry in a future pass.

### UI Polish — Deferred
Rich dashboard is functional. Do not spend time on formatting improvements
before data quality is validated via full 500-ticker log audit.

## Open Items
| Item | Priority | Target |
|---|---|---|
| Telegram delivery test | HIGH | v1.1 |
| Full scan log audit | HIGH | v1.1 |
| NYSE holiday guard | MEDIUM | v1.1 |
| CSV export | MEDIUM | v1.1 |
| Secondary ex-date source | LOW | v1.2 |
| Ex-date revision / dedup TTL | LOW | v1.2 |
| Threading / scan speed | LOWEST | after reliability proven |
