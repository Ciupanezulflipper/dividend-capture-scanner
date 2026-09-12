# DQP — AI START HERE

Last verified: 2026-09-12

## Purpose

This is the authoritative short continuity handoff for the Dividend Quality Pullback Scanner (DQP).

Repository: `Ciupanezulflipper/dividend-capture-scanner`
Runtime: Termux at `/data/data/com.termux/files/home/dividend-capture-scanner`
Default branch: `main`
Repository visibility verified 2026-09-10: **public**.

GitHub plus verified runtime/data evidence are authoritative. Obsidian is a knowledge/navigation mirror and must not override GitHub/runtime evidence.

## Current production/runtime state

- Telegram transient-delivery retry fix is implemented on `main` and deployed to the Termux runtime.
- GitHub implementation commits:
  - `cfb2a2b77062c2da421e0ee53448539545a4678c`
  - `140f1b7905dcc8dadfaf190c03c1d7dc24470799`
- Runtime deployment was verified by `git pull --ff-only origin main` advancing local `main` from `abde4ee` to `140f1b7`.
- Telegram delivery regression suite passed in Termux: **8/8 tests PASS**.
- Required clean-signal Telegram messages retry only on transient `transport_error` failures, with two bounded retries after short delays.
- Telegram API rejections are not retried.
- Heartbeat behavior remains independent from signal delivery.
- Signal history is committed only after verified successful Telegram delivery.

## Sep 10 incident — ITW

On the 2026-09-10 scheduled scan:

- Universe scanned: 503.
- ITW qualified as the one clean signal.
- ITW signal snapshot: price ~268.69, MA200 ~264.88, RSI14 ~34.3, dividend yield ~2.56%, ex-date 2026-09-30, HIGH priority.
- Telegram signal delivery was attempted once by the old code and failed with `ConnectionResetError(104, 'Connection reset by peer')`.
- About five seconds later the daily heartbeat delivered successfully with HTTP 200.
- `history.json` was intentionally not modified because the ITW alert was not delivered.
- Run health correctly recorded `scanner_exit_code=23`, `telegram_delivery_not_verified`, signal attempt=1, signal failure=1, signal success=0.

Classification: **QUALIFIED_BUT_DELIVERY_FAILED**. This was a transient delivery-control defect, not deduplication and not a strategy-selection defect.

Correction: bounded retry for required clean-signal transport failures only. No strategy thresholds were changed.

## Sep 11 live validation — four delivered signals

The next production run provided the first strong live validation after the retry fix.

Runtime reconciliation proved:

- CSV `signal_passed=true` rows: 9.
- Clean-only Telegram gate delivered exactly 4 signals: **ESS, FRT, OMC, WTW**.
- Five additional passed rows were correctly skipped as non-clean by `telegram_clean_only_non_clean_signal`: FDX, GRMN, DOC, PKG, TROW.
- All four clean signals had `attempted=true`, `delivered=true`, `outcome=delivered`, HTTP 200.
- `history.json` and `history.json.last-good` are semantically equal.
- No delivered Sep 11 signal is missing from history.
- No failed signal was incorrectly written to history.
- History count advanced exactly **20 -> 24**.
- ITW remains excluded, correctly.

New delivered signal snapshots:

| Symbol | Alerted at UTC | Price | Ex-date | Yield % | RSI | MA200 |
|---|---|---:|---|---:|---:|---:|
| ESS | 2026-09-10T14:40:46.599791+00:00 | 274.37 | 2026-09-30 | 3.776 | 36.07 | 263.999 |
| FRT | 2026-09-10T14:40:48.533577+00:00 | 115.16 | 2026-10-01 | 4.029 | 34.30 | 109.986 |
| OMC | 2026-09-10T14:40:49.966731+00:00 | 78.30 | 2026-09-18 | 4.087 | 35.88 | 77.189 |
| WTW | 2026-09-10T14:40:51.298522+00:00 | 313.72 | 2026-09-30 | 1.224 | 37.96 | 298.864 |

Important date note: the runtime `alerted_at` timestamps are UTC and fall on 2026-09-10 UTC, while the Telegram heartbeat/user-facing market date was Sep 11 in the scanner's market-date framing. Preserve runtime timestamps exactly; do not rewrite them to match display labels.

## Heartbeat result on Sep 11

The four required clean-signal deliveries all succeeded.

The heartbeat itself failed after transport timeout:

- attempted=true
- delivered=false
- outcome=`transport_error`
- detail: Telegram read timeout (15 seconds)
- `TELEGRAM_REQUIRED_DELIVERY_FAILED count=1 items=heartbeat`

Therefore `run_health.success=false` and `scanner_exit_code=23` were truthful for the run even though all four clean signals were successfully delivered.

This is an observability/reliability note, not a signal-loss incident. Do not change signal logic because of it.

## Frozen delivered-signal baseline

`history.json` now contains **24 delivered/tracked signals**.

Stored schema:

`alerted_at, days_away, dividend_yield_pct, ex_date, ma, price, rsi, symbol`

Baseline symbols:

`TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED, ESS, FRT, OMC, WTW`

Data-quality note: EA, JNJ and ED have stored `dividend_yield_pct=0.0`. Preserve the historical snapshot as-is and flag this when evaluating strategy results; do not rewrite history silently.

ITW remains separate as `QUALIFIED_BUT_DELIVERY_FAILED` and must not be retroactively inserted into delivered history.

## Strategy evaluation contract — LOCKED

Do not judge the strategy by whether a stock eventually rises. For every delivered signal, evaluate from the frozen signal price:

1. maximum drawdown after the alert;
2. first date price reaches +3% and trading days elapsed;
3. first date price reaches +5% and trading days elapsed;
4. return at T+1, T+3, T+5, T+10 and T+20 trading days;
5. dividend-adjusted total return where applicable;
6. SPY return over the identical holding window.

Portfolio-level metrics:

- % reaching +3% within 20 trading days;
- % reaching +5% within 20 trading days;
- median trading days to +3% and +5%;
- median and worst maximum drawdown;
- T+20 win rate;
- median T+20 total return;
- relative performance vs SPY.

If +3%/+5% is not reached within 20 trading days, record `NOT_REACHED_T20`; do not wait indefinitely.

The mature historical cohort remains ready for T+20 analysis. PSA, ESS, FRT, OMC and WTW are prospective/current forward-validation cases.

## Current operating decision

**ENGINEERING: HOLD**

**OPERATIONS: MONITOR**

**STRATEGY EVALUATION: READY**

Do not change thresholds, strategy filters, schema, ledger design, or infrastructure unless new evidence demonstrates a real defect.

Monitor only:

1. weekday 10:00 New York run executes;
2. clean signals, when present, are delivered successfully;
3. delivered signals enter `history.json`;
4. failed deliveries do not enter history;
5. heartbeat/runtime status remains truthful.

## Next high-value task

Run the mature-signal performance study under the locked evaluation contract while allowing production to operate unchanged.

Keep:
- PSA, ESS, FRT, OMC, WTW as prospective cases;
- ITW separate as `QUALIFIED_BUT_DELIVERY_FAILED`.

Do not resume ledger redesign or broader infrastructure work unless performance or runtime evidence requires it.

## Starting a new chat

A new DQP chat should:

1. read this file first;
2. inspect current GitHub `main`;
3. inspect current Termux runtime evidence before changing anything;
4. preserve the 24-signal delivered baseline and ITW exception;
5. avoid strategy changes until the performance study provides evidence.

Never assume a GitHub implementation is deployed until runtime proves it.
