# Dividend Capture Scanner

Private Python automation tool for scanning S&P 500 dividend-capture candidates.

## Current status

- Termux smoke test: PASS
- Scanner starts successfully
- S&P 500 list loads successfully
- Dashboard renders successfully
- Dry-run does not send Telegram
- Dry-run does not create history.json
- Trade execution: not included

## Smoke test

Run:

    ./run_bot.sh --dry-run --limit 10 --show-all

## Security

Never commit .env, Telegram secrets, history.json, logs, or .termux_req_sha256.

## Known v1 limitations

- No NYSE holiday guard yet.
- yfinance data may be stale or incomplete.
- Signals require manual validation.
- This is not a trading bot.
