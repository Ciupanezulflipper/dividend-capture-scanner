# DQP Decision Record — Runtime Delivery + Evaluation Contract

Date: 2026-09-10
Last reconciled: 2026-09-12
Status: ACCEPTED

## Decision

1. Fix the proven Telegram transient-delivery defect with bounded retries for required clean-signal `transport_error` failures only.
2. Do not retry API rejections.
3. Keep the invariant that `history.json` is updated only after verified successful signal delivery.
4. Keep ITW outside delivered history and classify it as `QUALIFIED_BUT_DELIVERY_FAILED`.
5. Hold further strategy engineering unless new evidence proves another defect.
6. Evaluate delivered signals using maximum drawdown, +3%/+5% first-hit timing, fixed T+ checkpoints, dividend-adjusted total return, and SPY comparison.

## Evidence

### Sep 10 ITW runtime evidence

The scheduled scan identified ITW as the clean signal. Telegram delivery failed with a transient connection reset. The heartbeat then delivered successfully about five seconds later. `history.json` was not modified because the signal alert was not verified as delivered.

This proved a narrow reliability defect: a transient Telegram transport failure can lose a valid signal even when connectivity recovers seconds later.

### Correction evidence

Implementation commits:

- `cfb2a2b77062c2da421e0ee53448539545a4678c`
- `140f1b7905dcc8dadfaf190c03c1d7dc24470799`

Termux runtime was fast-forwarded to `140f1b7` and the Telegram delivery regression suite passed **8/8**.

### Sep 11 live validation

The next live run delivered four clean signals:

- ESS
- FRT
- OMC
- WTW

Evidence:
- attempted=4
- delivered=4
- failures=0
- every delivered signal returned HTTP 200
- history count advanced **20 -> 24**
- `history.json` and `history.json.last-good` are semantically equal
- delivered-but-not-history = empty
- invalid history writes = empty
- ITW remains absent, correctly

The same run's heartbeat timed out after the four signals were already delivered, so run-level `success=false` / exit 23 remained truthful. This did not affect signal delivery or history integrity.

## Delivered baseline

Current delivered/tracked signal count: **24**.

Symbols:

`TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED, ESS, FRT, OMC, WTW`

EA, JNJ and ED retain stored `dividend_yield_pct=0.0`. Preserve those snapshots and flag them as data-quality limitations.

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

Prospective/current cases:
- PSA
- ESS
- FRT
- OMC
- WTW

Separate non-delivered case:
- ITW — `QUALIFIED_BUT_DELIVERY_FAILED`

Do not loosen thresholds or redesign the scanner because of signal frequency. Strategy changes must be driven by performance evidence.
