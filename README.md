# Dividend Capture Scanner

Private S&P 500 dividend-capture signal scanner.

## What It Does
Scans ~500 S&P 500 stocks daily and alerts when a stock satisfies all three conditions:
- Ex-dividend date within the next 21 days
- RSI(14) below 38 (oversold)
- Current price above the 200-day MA (uptrend intact)

Sends a Telegram alert for new signals. Deduplicates by `ticker|ex-date` so you are never spammed for the same event.

**This is a scanner only. It does not execute trades.**

## Status
| Item | Status |
|---|---|
| Repo created | YES |
| First commit pushed | YES — `eb5de68` |
| Branch | main |
| Termux smoke test | PASS |
| Telegram delivery test | PENDING (v1.1) |
| Secrets committed | NO |

## Files
| File | Purpose |
|---|---|
| `dividend_scanner.py` | Main scanner |
| `requirements.txt` | Core Python dependencies |
| `run_bot.sh` | Launcher (Termux + Linux venv) |
| `.env.example` | Credentials template |
| `.gitignore` | Excludes secrets and runtime files |

## Quick Start (Termux)
```bash
# 1. Clone
git clone git@github.com:Ciupanezulflipper/dividend-capture-scanner.git
cd dividend-capture-scanner

# 2. Uncomment TERMUX_MODE=1 in run_bot.sh
sed -i 's/^# TERMUX_MODE=1/TERMUX_MODE=1/' run_bot.sh
chmod +x run_bot.sh

# 3. Configure secrets
cp .env.example .env
nano .env   # fill in TELEGRAM_TOKEN and TELEGRAM_CHAT_ID

# 4. Smoke test (no Telegram, no history write)
./run_bot.sh --dry-run --limit 10 --show-all

# 5. Full live scan
./run_bot.sh
```

## Dependency Strategy
- **Core** (`requirements.txt`): pure Python, installs on Termux without native compilation
- **Optional** (attempted by `run_bot.sh`, non-fatal):
  - `lxml` — faster HTML parser; `html5lib` is the fallback
  - `pandas-ta` — preferred RSI; pure-pandas Wilder EWM is the fallback

## Crontab (Linux, UTC server clock)
```
CRON_TZ=America/New_York
0 10 * * 1-5 /path/to/dividend-capture-scanner/run_bot.sh >> /path/to/dividend-capture-scanner/cron.log 2>&1
```

## Signal Frequency
RSI < 38 + price above 200D MA + ex-date within 21 days is a sparse combination.
Zero signals for days or weeks is normal in a healthy market. Do not loosen thresholds.

## Never Commit
`.env` · `history.json` · `*.log` · `.venv/` · `.termux_req_sha256`

## v1 Limitations
- Does not skip NYSE market holidays
- yfinance ex-date data may be incomplete or stale
- No dividend safety check
- No earnings-date avoidance
- Manual validation required before acting on any signal
