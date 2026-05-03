# Dividend Quality Pullback Scanner

Private S&P 500 scanner for quality dividend stocks during controlled pullbacks.

> **Hypothesis-testing and stock discovery tool. Does not execute trades.**

## Thesis
Find quality dividend-paying S&P 500 companies that are temporarily oversold
while their long-term trend (200D MA) remains intact. Use the upcoming
ex-dividend date as a timing context filter, not as the primary edge.

Alerts are candidate research prompts. Manual validation required before acting.

## Signal Criteria (all required)
| Condition | Threshold |
|---|---|
| Ex-dividend date | Within next 21 calendar days |
| RSI(14) | Below 38 |
| Price vs 200D MA | Price above MA (trend intact) |

## Status
| Item | Status |
|---|---|
| First commit pushed | YES — eb5de68 |
| Termux smoke test | PASS |
| Telegram setup (@DividendQualityBot) | **DONE** |
| Weekend guard | **VERIFIED PASS** |
| Forced-weekend 10-ticker scan | **PASS — 0 signals** |
| Full 500-ticker scan + audit | **PENDING (v1.1 next)** |
| Secrets committed | NO |

## Known Data Quality Issue
yfinance returns stale ex-dates for some S&P 500 tickers.
Log evidence: ADBE returned 2005-03-24, AMD returned 1995-04-27.
These correctly skip the 21-day window filter. Full scan will quantify failure rate.

## Files
| File | Purpose |
|---|---|
| `dividend_scanner.py` | Main scanner |
| `requirements.txt` | Core Python dependencies (no native compilation) |
| `run_bot.sh` | Launcher — Termux and Linux venv modes |
| `.env.example` | Credentials template |
| `.gitignore` | Excludes secrets and runtime files |

## Quick Start (Termux)
```bash
git clone git@github.com:Ciupanezulflipper/dividend-capture-scanner.git
cd dividend-capture-scanner
sed -i 's/^# TERMUX_MODE=1/TERMUX_MODE=1/' run_bot.sh
chmod +x run_bot.sh
cp .env.example .env && nano .env
./run_bot.sh --dry-run --limit 10 --show-all   # smoke test
./run_bot.sh                                    # full live scan
```

## Scan Commands
```bash
# Smoke test — no Telegram, no history
./run_bot.sh --dry-run --limit 10 --show-all

# Weekend override for data-quality audit
./run_bot.sh --show-all --force-weekend

# Full live scan (run on a market day)
./run_bot.sh
```

## Dependency Strategy
- **Core** (`requirements.txt`): pure Python, no native compilation required
- **Optional** (non-fatal, attempted by `run_bot.sh`):
  - `lxml` — faster HTML parser; `html5lib` is the fallback
  - `pandas-ta` — preferred RSI; pure-pandas Wilder EWM is the fallback

## Crontab (Linux, UTC server clock)
```
CRON_TZ=America/New_York
0 10 * * 1-5 /path/to/dividend-capture-scanner/run_bot.sh >> cron.log 2>&1
```

## Signal Frequency
RSI < 38 + price above 200D MA + ex-date within 21 days is sparse.
Zero signals for days or weeks is **normal**. Do not loosen thresholds.

## Performance Tracking (required before drawing conclusions)
Every signal: record ticker, price, SPY price at signal date.
Measure returns vs SPY at 1/3/5/10/20 trading days.
Minimum 20-30 signals before drawing any conclusions.

## Never Commit
`.env` · `history.json` · `*.log` · `.venv/` · `.termux_req_sha256`

## v1 Limitations
- yfinance ex-date data proven to be stale for some tickers
- Does not skip NYSE market holidays
- No dividend safety, payout ratio, or earnings-date checks
- No position sizing, exit rules, or trade execution

## Repo Name Note
Repo is named `dividend-capture-scanner`. Product direction is now
"Dividend Quality Pullback Scanner". Rename deferred — conscious tech debt.
