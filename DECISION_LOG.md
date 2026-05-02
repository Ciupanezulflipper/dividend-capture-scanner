# DECISION_LOG.md

## Locked Decisions

- Canonical main file: dividend_scanner.py
- v1 scope: scanner and alerter only
- No trade execution
- .env must never be committed
- history.json and logs must never be committed
- .termux_req_sha256 must never be committed
- Dedup key: ticker plus ex-date
- RSI rule: RSI(14) below 38
- Trend rule: current price above 200-day moving average
- Ex-date window: next 21 calendar days
- Termux mode: no venv, auto-detected
- lxml: optional only
- pandas-ta: optional only
- html5lib and beautifulsoup4: core parser fallback
- Market holidays: documented v1 limitation, defer NYSE calendar to v1.1
