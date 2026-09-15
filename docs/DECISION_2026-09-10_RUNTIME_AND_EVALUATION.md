# DQP Decision Record — Runtime Delivery + Evaluation Contract

Date: 2026-09-10
Last reconciled through runtime evidence dated: 2026-09-16
Status: ACCEPTED

## Decision

1. Fix the proven Telegram transient-delivery defect with bounded retries for required clean-signal `transport_error` failures only.
2. Do not retry API rejections.
3. Keep the invariant that `history.json` is updated only after verified successful signal delivery.
4. Preserve failed-delivery incidents separately from later successful signal occurrences.
5. Hold further strategy engineering unless new evidence proves another defect.
6. Evaluate delivered signals using maximum drawdown, +3%/+5% first-hit timing, fixed T+ checkpoints, dividend-adjusted total return, and SPY comparison.

## Original Sep 10 ITW evidence

ITW qualified as the clean signal. Telegram delivery failed with a transient connection reset. `history.json` was not modified because delivery was not verified.

This occurrence remains classified:

`QUALIFIED_BUT_DELIVERY_FAILED`

It justified the bounded retry correction.

## Correction evidence

Implementation commits:

- `cfb2a2b77062c2da421e0ee53448539545a4678c`
- `140f1b7905dcc8dadfaf190c03c1d7dc24470799`

Termux regression suite passed **8/8** after deployment.

## Sep 11 live evidence

Four clean signals were delivered successfully:

- ESS
- FRT
- OMC
- WTW

History advanced **20 -> 24** with no delivered-but-missing or invalid writes.

## Sep 15 live evidence

Three clean signals delivered successfully with HTTP 200:

- APD
- ITW
- INVH

History advanced **24 -> 27**.

Primary and last-good history snapshots both contained 27 rows and were semantically equal.

The Sep 15 ITW occurrence is a later valid signal. It must remain in delivered history while the Sep 10 failed occurrence remains separately preserved in the incident record.

## Sep 16 deduplication evidence

Signal-generated candidates included APD, FRT, INVH, KVUE and LRCX.

Clean candidates were APD, FRT and INVH. Each was already recorded in history, so deduplication correctly prevented repeat alerts.

KVUE and LRCX were correctly skipped by the clean-only gate.

No new history entries were written.

Heartbeat delivered successfully.

This confirms that `Clean signals` in the heartbeat represents clean candidates identified in the daily scan, while actual Telegram signal messages are further reduced by deduplication.

## Current delivered baseline

Current delivered/tracked signal count: **27**.

Symbols:

`TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED, ESS, FRT, OMC, WTW, APD, ITW, INVH`

EA, JNJ and ED retain stored `dividend_yield_pct=0.0`. Preserve those snapshots and flag them during performance analysis.

## Evaluation contract

For every delivered signal, use the frozen alert price and record:

- maximum drawdown after alert;
- first +3% price-hit date and trading days elapsed;
- first +5% price-hit date and trading days elapsed;
- T+1, T+3, T+5, T+10 and T+20 returns;
- dividend-adjusted total return where applicable;
- SPY return over the same dates.

If +3% or +5% is not reached within 20 trading days, record `NOT_REACHED_T20`.

Aggregate metrics:

- +3% hit rate within T+20;
- +5% hit rate within T+20;
- median days to each target;
- median and worst maximum drawdown;
- T+20 win rate;
- median T+20 total return;
- outperformance versus SPY.

## Current operating rule

**ENGINEERING: HOLD**

**OPERATIONS: MONITOR**

**STRATEGY EVALUATION: READY**

No new repository or strategy change is justified by the Sep 15/16 evidence.

Strategy changes must be driven by the performance study, not by signal frequency or repeated daily candidates.
