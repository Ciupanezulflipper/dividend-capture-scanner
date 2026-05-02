# STRATEGY_HISTORY.md

## v1 Strategy — Oversold Dividend-Capture Scanner

### Universe
- Dynamically fetch S&P 500 from Wikipedia each run
- `requests.get` with `User-Agent` -> `StringIO` -> `pd.read_html(flavor="html5lib")`
- No hard-coded ticker list

### Dividend Filter
- Ex-dividend date inside a rolling 21-calendar-day window from scan date
- Dedup key: `ticker|ex_date` (not ticker alone — quarterly dividends recur)

### Technical Filter
Both conditions required:
- RSI(14) < 38
- Current price > 200-day MA

### RSI Engine
- Primary (optional): `pandas-ta` if installed
- Fallback (always present): pure-pandas Wilder EWM
- `pandas-ta` must never block startup

### Alert Format
```
BUY SIGNAL: [Ticker] | Yield: [X]% | RSI: [X] | Ex-Date: [Date]
```

### State Management
- `history.json`: stores `ticker|ex_date` keys of alerted signals
- Never committed to Git
- Corrupt history backed up safely, not silently trusted
- `--dry-run` must never write `history.json`

### Logging
- Per-ticker: scanned / skipped / duplicate / error / alerted
- Log files never committed

## v1 Known Limitations
- yfinance data may be incomplete or stale
- NYSE holidays not blocked
- No dividend safety check
- No earnings-date avoidance
- No position sizing, exit rules, or execution

## Signal Frequency Expectation
RSI < 38 AND price > 200D MA AND ex-date within 21 days is a **sparse** condition set.
In a healthy/bull market, zero signals for days or weeks is **normal**.
**Do not loosen RSI threshold to chase signals.** The rarity is the feature, not a bug.

## Smoke Test History
| Date | Command | Result |
|---|---|---|
| 2026-05-01 | `./run_bot.sh --dry-run --limit 10 --show-all` | PASS |

## First Commit
- Hash: `eb5de68`
- Branch: `main`
- Status: pushed to GitHub

## v1.1 Planned Improvements (locked order)
1. `.env` setup + Telegram delivery test
2. Full 500-ticker scan + log audit (error rate, ex-date coverage)
3. NYSE holiday / trading-day guard
4. CSV export / report mode
5. Secondary ex-dividend validation source

## v1.2 Candidates
- Ex-date revision detection (dedup key TTL or revision check)
- Dividend safety filter
- Earnings-date avoidance
- Sector concentration control
- Scan optimisation (threading/async) — only after reliability proven
