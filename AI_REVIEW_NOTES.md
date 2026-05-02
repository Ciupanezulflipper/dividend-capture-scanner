# AI_REVIEW_NOTES.md

## Verified AI/Manual Review Notes — 2026-05-01

Claude generated the initial implementation files. ChatGPT/Termux testing found and fixed these issues:

1. lxml hard dependency failed on Termux.
2. pandas-ta should not block startup because pure-pandas RSI fallback exists.
3. pandas.read_html defaulted to lxml.
4. Wikipedia returned HTTP 403 when using direct pandas URL fetch.
5. pandas warned literal HTML should be wrapped in StringIO.
6. StringIO import was missing after the parser fix.

Current verified smoke test:

    ./run_bot.sh --dry-run --limit 10 --show-all

Result:
- PASS.
- Scanner starts.
- S&P 500 loads.
- 10 tickers scan.
- Dashboard renders.
- No Telegram in dry-run.
- No history.json in dry-run.

Open v1 limitations:
- No NYSE holiday guard yet.
- yfinance ex-dividend data must be manually validated.
- No trade execution.
