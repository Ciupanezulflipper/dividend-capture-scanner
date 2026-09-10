# Dividend Scanner — Current State

Last reviewed: 2026-09-10

> Navigation/knowledge mirror. GitHub and verified runtime/data evidence are authoritative.

## Repository

`Ciupanezulflipper/dividend-capture-scanner`

Primary continuity entrypoint: `AI_START_HERE.md`

## Current status

- **ENGINEERING: HOLD**
- **OPERATIONS: MONITOR**
- **STRATEGY EVALUATION: READY**

Telegram transient signal-delivery retry fix is implemented on GitHub and deployed to Termux. Runtime regression test result: **8/8 PASS**.

Implementation commits:
- `cfb2a2b77062c2da421e0ee53448539545a4678c`
- `140f1b7905dcc8dadfaf190c03c1d7dc24470799`

## Sep 10 ITW incident

ITW was the one clean signal on the Sep 10 scan. Telegram delivery was attempted and failed with a transient connection reset. The heartbeat succeeded roughly five seconds later. ITW was correctly not written to `history.json` because delivery was not verified.

Classification: `QUALIFIED_BUT_DELIVERY_FAILED`.

Correction: required signal messages now receive up to two bounded retries on `transport_error` only. API rejections are not retried. Heartbeat semantics and history-after-success invariant remain unchanged.

See GitHub incident record:
`docs/INCIDENT_2026-09-10_ITW_TELEGRAM_TRANSPORT.md`

## Frozen delivered-signal baseline

20 signals are currently in runtime `history.json`:

TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED.

PSA is the newest delivered forward-validation case. ITW is not part of delivered history.

Historical data-quality note: EA, JNJ and ED have stored dividend yield `0.0`; preserve those snapshots and flag them during analysis rather than rewriting history.

## Evaluation contract

For each delivered signal track:

- signal/alert price;
- maximum drawdown;
- first +3% date and trading days;
- first +5% date and trading days;
- T+1, T+3, T+5, T+10, T+20 returns;
- dividend-adjusted total return where applicable;
- SPY return over identical dates.

If +3%/+5% is not reached within 20 trading days, record `NOT_REACHED_T20`.

Aggregate metrics: +3% and +5% hit rates, median time to target, median/worst drawdown, T+20 win rate, median T+20 total return, and outperformance versus SPY.

19 signals are mature enough for T+20 analysis. PSA remains prospective.

## Operating rule

For the next 3–5 trading days, do not change thresholds, strategy logic, schema, ledger, or infrastructure unless new evidence proves a defect.

Verify only:
1. weekday 10:00 New York run executes;
2. clean signals, when present, are delivered before/with the heartbeat;
3. successful deliveries enter `history.json`; failed deliveries do not.

## Next step

Begin the 19-case mature-signal performance study while production runs unchanged.
