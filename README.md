# Dividend Quality Pullback Scanner

Private S&P 500 scanner for quality dividend stocks during controlled pullbacks.

> **Hypothesis-testing and stock discovery tool. Does not execute trades.**

## Thesis
Find quality dividend-paying S&P 500 companies that are temporarily oversold
while their long-term trend (200D MA) remains intact. Use the upcoming
ex-dividend date as a timing context filter, not as the primary edge.

Alerts are candidate research prompts. Manual validation required before acting.

## Signal Criteria — Active Logic
These are the current hard signal criteria:

| Condition | Threshold |
|---|---|
| Ex-dividend date | Within next 21 calendar days |
| RSI(14) | Below 38 |
| Price vs 200D MA | Price above MA (trend intact) |

## Audit-Only Candidate Filters
v1.1 measures these but does **not** hard-filter signals with them yet:

| Candidate Filter | Audit Default | Status |
|---|---:|---|
| Minimum dividend yield | 1.0% | Audit-only |
| Minimum days to ex-date | 7 days | Audit-only |

These were added because early live alerts exposed two issues:
- EA passed technically but had weak dividend-quality fit because of low yield.
- ED passed technically but had only 5 days before ex-date.

Do not activate these as hard filters until the full 500-ticker audit quantifies impact.

## Status
| Item | Status |
|---|---|
| First commit pushed | YES — eb5de68 |
| Current main commit | f2949d4 |
| Termux smoke test | PASS |
| Telegram setup (@DividendQualityBot) | DONE |
| Telegram live alert path | PROVEN — ED, EA, JNJ fired on 2026-05-07 |
| Weekend guard | VERIFIED PASS |
| Forced-weekend 10-ticker scan | PASS |
| v1.1 audit/report layer | MERGED — PR #1 |
| CSV report output | IMPLEMENTED |
| Reason-count summary | IMPLEMENTED |
| Audit-only yield/day flags | IMPLEMENTED |
| Full 500-ticker audit | PENDING |
| Secrets committed | NO |

## v1.1 Report Output
Each scan writes an audit CSV unless disabled with `--no-report`:

```text
reports/scan_report_YYYY-MM-DD.csv
```

Report columns:

```text
scan_date,symbol,ex_date,days_to_ex_date,price,ma200,rsi14,dividend_yield_pct,signal_passed,reason_category,audit_flags,passes_audit_min_yield,passes_audit_min_days_to_ex_date,error
```

Reason categories:
- `no_ex_date_available`
- `stale_or_past_ex_date`
- `ex_date_outside_window`
- `yfinance_error`
- `technical_failed_rsi`
- `technical_failed_ma200`
- `signal_generated`

Audit flags:
- `valid_forward_ex_date_in_window`
- `low_yield_candidate`
- `ex_date_too_close_candidate`

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
| `CONTINUITY.md` | Project state and handoff log |
| `DECISION_LOG.md` | Locked decisions |
| `AI_REVIEW_NOTES.md` | Review notes for cross-AI audit |
| `STRATEGY_HISTORY.md` | Strategy/thesis history |

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
./run_bot.sh --dry-run --show-all --force-weekend

# Full live scan (run on a market day)
./run_bot.sh

# Full 500-ticker audit/report run without Telegram or history writes
./run_bot.sh --dry-run --show-all

# Custom audit-only candidate thresholds
./run_bot.sh --dry-run --show-all --audit-min-yield 1.0 --audit-min-days-to-ex-date 7
```

## Dependency Strategy
- **Core** (`requirements.txt`): pure Python, no native compilation required
- **Optional** (non-fatal, attempted by `run_bot.sh`):
  - `lxml` — faster HTML parser; `html5lib` is the fallback
  - `pandas-ta` — preferred RSI; pure-pandas Wilder EWM is the fallback

## Crontab
```
CRON_TZ=America/New_York
0 10 * * 1-5 cd /data/data/com.termux/files/home/dividend-capture-scanner && ./run_bot.sh >> cron_dividend_bot.log 2>&1
```

## Signal Frequency
RSI < 38 + price above 200D MA + ex-date within 21 days is sparse.
Zero signals for days or weeks is **normal**. Do not loosen thresholds.

## Performance Tracking (required before drawing conclusions)
Every signal: record ticker, price, SPY price at signal date.
Measure returns vs SPY at 1/3/5/10/20 trading days.
Minimum 20-30 signals before drawing any conclusions.

## Never Commit
`.env` · `history.json` · `*.log` · `.venv/` · `.termux_req_sha256` · `reports/`

## v1 Limitations
- yfinance ex-date data proven to be stale for some tickers
- Does not skip NYSE market holidays
- No dividend safety, payout ratio, or earnings-date checks
- No position sizing, exit rules, or trade execution
- Minimum yield and minimum days-to-ex-date are measured but not active filters yet

## Current Next Step
Run the full 500-ticker dry-run audit on a market day, then review the CSV and reason-count summary before changing strategy logic.

## Repo Name Note
Repo is named `dividend-capture-scanner`. Product direction is now
"Dividend Quality Pullback Scanner". Rename deferred — conscious tech debt.
