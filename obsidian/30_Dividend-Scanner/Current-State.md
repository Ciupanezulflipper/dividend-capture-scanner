# Dividend Scanner — Current State

Last reviewed: 2026-09-12

> Navigation/knowledge mirror. GitHub and verified runtime/data evidence are authoritative.

## Repository

`Ciupanezulflipper/dividend-capture-scanner`

Primary continuity entrypoint: `AI_START_HERE.md`

## Current status

- **ENGINEERING: HOLD**
- **OPERATIONS: MONITOR**
- **STRATEGY EVALUATION: READY**

Telegram transient signal-delivery retry fix is deployed to Termux. Runtime regression result: **8/8 PASS**.

Implementation commits:
- `cfb2a2b77062c2da421e0ee53448539545a4678c`
- `140f1b7905dcc8dadfaf190c03c1d7dc24470799`

## Sep 10 ITW incident

ITW qualified as a clean signal but Telegram delivery failed on a transient connection reset. ITW was correctly not written to history.

Classification: `QUALIFIED_BUT_DELIVERY_FAILED`.

Correction: required signal messages retry bounded transient `transport_error` failures. API rejections are not retried.

## Sep 11 live validation

Four clean signals were successfully delivered:

- ESS
- FRT
- OMC
- WTW

All four had verified HTTP 200 Telegram delivery and were appended to `history.json`.

History reconciliation:
- previous count: 20
- current count: 24
- delivered-but-not-history: none
- invalid history writes: none
- primary and last-good history snapshots: semantically equal
- ITW remains excluded

New forward cases:

| Symbol | Price | Ex-date | Yield % | RSI | MA200 |
|---|---:|---|---:|---:|---:|
| ESS | 274.37 | 2026-09-30 | 3.776 | 36.07 | 263.999 |
| FRT | 115.16 | 2026-10-01 | 4.029 | 34.30 | 109.986 |
| OMC | 78.30 | 2026-09-18 | 4.087 | 35.88 | 77.189 |
| WTW | 313.72 | 2026-09-30 | 1.224 | 37.96 | 298.864 |

The same run's heartbeat timed out after the four signal deliveries succeeded, so run health correctly reported failure/exit 23. This did not lose any signal.

## Current delivered baseline

24 tracked signals:

TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED, ESS, FRT, OMC, WTW.

EA, JNJ and ED retain stored dividend yield 0.0; preserve those snapshots and flag them during analysis.

## Evaluation contract

For every delivered signal track:

- frozen alert price
- maximum drawdown
- first +3% date and trading days
- first +5% date and trading days
- T+1/T+3/T+5/T+10/T+20 returns
- dividend-adjusted total return
- SPY return over identical dates

If +3%/+5% is not reached within 20 trading days, record `NOT_REACHED_T20`.

## Prospective cases

- PSA
- ESS
- FRT
- OMC
- WTW

Separate:
- ITW — `QUALIFIED_BUT_DELIVERY_FAILED`

## Operating rule

Do not change thresholds, strategy logic, schema, ledger, or infrastructure unless new evidence proves a defect.

Next high-value task: mature-signal performance study while production continues unchanged.
