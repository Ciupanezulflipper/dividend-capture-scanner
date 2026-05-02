# STRATEGY_HISTORY.md

## v1 Strategy

Universe:
- Current S&P 500 list from Wikipedia.

Dividend filter:
- Forward ex-dividend date inside next 21 calendar days.

Technical filter:
- RSI(14) below 38.
- Current price above 200-day moving average.

State:
- history.json prevents duplicate alerts by ticker plus ex-date.
- dry-run must not write history.json.

Alert:
- Telegram alert only outside dry-run and only when credentials exist.

Latest smoke test:
- Date: 2026-05-01
- Command: ./run_bot.sh --dry-run --limit 10 --show-all
- Result: PASS
- Signals found: 0
