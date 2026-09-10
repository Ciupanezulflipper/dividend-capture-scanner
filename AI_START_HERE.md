# DQP — AI START HERE

Last verified: 2026-09-10

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
- Heartbeat behavior is unchanged.
- Signal history is committed only after verified successful Telegram delivery.

## Sep 10 incident — ITW

On the 2026-09-10 scheduled scan:

- Universe scanned: 503.
- ITW qualified as the one clean signal.
- ITW signal snapshot: price ~268.69, MA200 ~264.88, RSI14 ~34.3, dividend yield ~2.56%, ex-date 2026-09-30, HIGH priority.
- Telegram signal delivery was attempted once by the old code and failed with `ConnectionResetError(104, 'Connection reset by peer')`.
- About five seconds later the daily heartbeat was delivered successfully with HTTP 200.
- `history.json` was intentionally not modified because the ITW alert was not delivered.
- Run health correctly recorded `scanner_exit_code=23`, `telegram_delivery_not_verified`, signal attempt=1, signal failure=1, signal success=0.

Classification: **QUALIFIED_BUT_DELIVERY_FAILED**. This was a transient delivery-control defect, not deduplication and not a strategy-selection defect.

Correction: bounded retry for required clean-signal transport failures only. No strategy thresholds were changed.

## Frozen delivered-signal baseline

`history.json` contains **20 delivered/tracked signals**. The stored schema is:

`alerted_at, days_away, dividend_yield_pct, ex_date, ma, price, rsi, symbol`

Baseline:

| # | Symbol | Alerted at UTC | Price | Ex-date | Yield % | RSI |
|---:|---|---|---:|---|---:|---:|
| 1 | TGT | 2026-05-12T03:58:23.507829+00:00 | 118.44 | 2026-05-13 | 3.85 | 37.3 |
| 2 | TRV | 2026-06-01T14:39:06.266820+00:00 | 289.46 | 2026-06-10 | 1.73 | 33.8 |
| 3 | WMB | 2026-06-01T14:39:07.689692+00:00 | 70.37 | 2026-06-12 | 2.98 | 35.8 |
| 4 | AEE | 2026-06-01T14:39:03.749511+00:00 | 105.57 | 2026-06-09 | 2.84 | 36.3 |
| 5 | PCAR | 2026-05-12T03:55:32.438092+00:00 | 112.96 | 2026-05-13 | 1.24 | 36.2 |
| 6 | EA | 2026-05-07T14:07:55.233488+00:00 | 200.79 | 2026-05-27 | 0.00 | 35.1 |
| 7 | CB | 2026-05-29T14:31:06.884894+00:00 | 313.06 | 2026-06-12 | 1.30 | 35.7 |
| 8 | JNJ | 2026-05-07T14:10:46.192673+00:00 | 224.62 | 2026-05-26 | 0.00 | 37.1 |
| 9 | NEE | 2026-05-26T14:26:57.275141+00:00 | 87.93 | 2026-06-05 | 2.83 | 37.7 |
| 10 | PSA | 2026-09-07T14:30:41.696248+00:00 | 302.01 | 2026-09-15 | 3.97 | 33.9 |
| 11 | DVN | 2026-05-29T14:31:08.191013+00:00 | 43.78 | 2026-06-15 | 2.38 | 34.9 |
| 12 | BALL | 2026-05-12T03:45:15.579423+00:00 | 57.72 | 2026-06-01 | 1.39 | 38.0 |
| 13 | APA | 2026-07-01T14:18:32.442017+00:00 | 32.34 | 2026-07-22 | 3.09 | 33.9 |
| 14 | TPL | 2026-05-12T03:58:38.931235+00:00 | 402.63 | 2026-06-01 | 0.60 | 36.1 |
| 15 | EOG | 2026-07-01T14:18:32.636782+00:00 | 128.35 | 2026-07-17 | 3.18 | 37.7 |
| 16 | REG | 2026-06-02T14:23:14.621718+00:00 | 76.03 | 2026-06-12 | 3.97 | 37.5 |
| 17 | TJX | 2026-05-12T03:58:46.212488+00:00 | 148.91 | 2026-05-14 | 1.29 | 29.6 |
| 18 | FCX | 2026-07-07T14:17:07.868767+00:00 | 58.83 | 2026-07-15 | 1.02 | 37.7 |
| 19 | HUBB | 2026-05-12T03:51:26.286346+00:00 | 490.16 | 2026-05-29 | 1.16 | 37.0 |
| 20 | ED | 2026-05-07T14:06:10.182132+00:00 | 106.87 | 2026-05-13 | 0.00 | 37.6 |

Data-quality note: EA, JNJ and ED have stored `dividend_yield_pct=0.0`. Preserve the historical snapshot as-is and flag this when evaluating strategy results; do not rewrite history silently.

Current structured log retention proves PSA delivery and shows no `DELIVERED_BUT_NOT_HISTORY` mismatch. Older history entries predate the currently retained structured Telegram-delivery log, so absence from that log must not be interpreted as proof they were never delivered.

## Strategy evaluation contract — LOCKED for next phase

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

19 of the 20 delivered signals are mature enough for T+20 analysis. PSA remains a live forward-validation case. ITW must be tracked separately as `QUALIFIED_BUT_DELIVERY_FAILED`, not retroactively inserted into delivered history.

## Current operating decision

**ENGINEERING: HOLD**

**OPERATIONS: MONITOR**

**STRATEGY EVALUATION: READY**

For the next 3–5 trading days, make no strategy/filter/schema/ledger changes unless new evidence demonstrates a real defect. Verify only:

1. weekday 10:00 New York run executes;
2. if a clean signal exists, the signal is delivered before/with the heartbeat;
3. successfully delivered clean signals appear in `history.json` and failed deliveries do not.

Do not loosen RSI or other strategy thresholds because of low signal count.

## Next high-value task

Run the first 19-case mature-signal performance study under the locked evaluation contract while allowing the production scanner to operate unchanged. Keep PSA prospective. Do not resume ledger redesign or broader infrastructure work unless the performance or runtime evidence requires it.

## Starting a new chat

A new DQP chat should read this file first, then inspect current GitHub `main`, then ask for or inspect current Termux runtime evidence before changing anything. Never assume a GitHub implementation is deployed until runtime proves it.
