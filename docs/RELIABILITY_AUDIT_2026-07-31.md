# Dividend Quality Pullback Scanner Reliability Audit — 2026-07-31

## Scope

Repository: `Ciupanezulflipper/dividend-capture-scanner`  
Audited main commit: `9de2d75eadcf3f382ad50380a301337287aa12e4`

This audit separates strategy logic, code health, scheduled execution, provider
availability, Telegram delivery, and cloud deployment. It does not claim that an
OCI resource exists or that Termux is continuously reliable.

## Strategy reconstruction

No merged commit or pull request implements 5%, 10%, or 15% price-drop gates.
The May 2026 reframe changed the thesis from dividend capture to a dividend
quality pullback candidate scanner. The active signal remains:

1. Ex-dividend date within 21 calendar days.
2. RSI(14) below 38.
3. Price above the 200-day moving average.

Yield of at least 1% and at least seven days to ex-date are audit flags used by
`--telegram-clean-only`; they are not raw signal-generation filters.

## Runtime evidence reconciled

- 2026-07-24: healthy 503-ticker scan and Telegram heartbeat received.
- 2026-07-27: provider collapse; history and signal delivery blocked; admin
  warning failed.
- 2026-07-28: healthy 503-ticker scan and Telegram heartbeat received.
- 2026-07-29: scan completed; FIX was non-clean because yield was 0.23%; daily
  heartbeat delivery failed.
- 2026-07-30: provider collapse; admin warning failed.
- 2026-07-31: scan completed; AEP and UDR were clean, PNW was too close to
  ex-date; both clean signals and the heartbeat failed delivery.

The observed failures include DNS resolution errors and TLS hostname mismatch.
The evidence does not identify Android battery management as the root cause.

## Confirmed defects on audited main

1. `run_bot.sh` contacts PyPI on every scheduled run by attempting to upgrade
   pip, setuptools, and wheel before checking its dependency stamp.
2. Provider collapse exits the scanner with code 0, so process supervision alone
   cannot distinguish a failed data run from success.
3. The provider-error classifier checks a narrow set of strings only in
   `yf_ex_date_error`. A controlled simulation showed that 90% DNS failures in
   the general `error` field, or exact `[Errno 7]` wording, can be reported as a
   healthy run when a small number of rows still contain dates and prices.
4. The scanner logs `Daily heartbeat sent.` and `Admin Telegram warning sent.`
   without checking the Boolean result from `send_telegram()`.
5. Scanner health describes provider health only. It does not prove Telegram
   delivery.
6. There is no committed scanner regression-test suite on main.
7. `load_history()` silently resets to an empty dictionary on malformed JSON and
   `save_history()` is non-atomic. These remain open defects because this branch
   intentionally avoids changing signal/history behavior without a complete
   scanner-file replacement and dedicated tests.
8. Telegram watchlist wording uses hard-coded 1% and seven-day thresholds even
   though audit thresholds are configurable. This remains open for the same
   scope-control reason.
9. The performance audit omits the documented +20 trading-day checkpoint, max
   drawdown, and sector analysis. Strategy changes remain blocked until the
   evidence set is expanded and validated.

## Changes in this branch

- Routine launches no longer contact PyPI before scanner execution.
- Dependency installation is explicit through `./run_bot.sh --install-deps`.
- A production wrapper validates scanner health, independently audits CSV
  provider failures, checks Telegram log evidence, writes an atomic run-health
  artifact, and returns non-zero on operational failure.
- Offline regression tests cover the exact DNS/TLS patterns observed in
  production and the false Telegram-success logging pattern.
- GitHub Actions runs shell, syntax, and offline reliability tests.

## Scope boundaries

- Scanner source and trading thresholds are unchanged.
- Cron configuration is unchanged.
- History behavior is unchanged.
- Report writing is unchanged.
- Telegram formatting is unchanged.
- OCI resources are not created.
- Termux remains the production fallback until cloud deployment is proven by
  several unattended runs.
