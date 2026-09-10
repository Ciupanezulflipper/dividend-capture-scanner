# DQP Decision Record — Runtime Delivery + Evaluation Contract

Date: 2026-09-10
Status: ACCEPTED

## Decision

1. Fix the proven Telegram transient-delivery defect with bounded retries for required clean-signal `transport_error` failures only.
2. Do not retry API rejections.
3. Do not change heartbeat behavior.
4. Keep the invariant that `history.json` is updated only after verified successful signal delivery.
5. Freeze the current 20 delivered-signal history as the baseline for performance evaluation.
6. Keep ITW outside delivered history and classify it as `QUALIFIED_BUT_DELIVERY_FAILED`.
7. Hold further engineering for 3–5 trading days unless new evidence proves another defect.
8. Begin strategy evaluation using maximum drawdown, +3%/+5% first-hit timing, fixed T+ checkpoints, dividend-adjusted total return, and SPY comparison.

## Evidence

### Sep 10 ITW runtime evidence

The scheduled 2026-09-10 scan identified ITW as the one clean signal. Telegram delivery was attempted and failed with a transient connection reset. Approximately five seconds later the daily heartbeat successfully delivered with HTTP 200. `history.json` was not modified because the signal alert was not verified as delivered.

This proves a narrow reliability defect: a transient Telegram transport failure can lose a valid signal even when connectivity recovers seconds later.

### Correction evidence

Implementation commits:

- `cfb2a2b77062c2da421e0ee53448539545a4678c`
- `140f1b7905dcc8dadfaf190c03c1d7dc24470799`

Termux runtime was fast-forwarded from `abde4ee` to `140f1b7` and the Telegram delivery regression suite passed **8/8**.

### Signal history evidence

The runtime `history.json` contains 20 delivered/tracked signals. Current retained structured Telegram logs contain PSA as a verified delivered signal and show no delivered signal missing from history. Older history rows predate retained structured delivery logs, so their absence from the current log is not evidence that they were not delivered.

Three historical rows — EA, JNJ and ED — contain stored `dividend_yield_pct=0.0`. Those snapshots must remain unchanged and be flagged as data-quality limitations during analysis.

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

## Consequences

The scanner is now in monitoring rather than feature-expansion mode. Low signal frequency alone is not a reason to loosen thresholds. Strategy changes must be driven by the performance study, not by impatience or isolated examples.

## Next step

Allow normal scheduled operation for 3–5 trading days while beginning the mature 19-case performance study. PSA remains prospective. ITW remains a documented missed qualifying signal and should not be retroactively inserted into delivered history.
