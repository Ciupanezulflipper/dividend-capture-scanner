# Dividend Scanner — Current State

Last reconciled through runtime evidence dated: 2026-09-16

> Navigation/knowledge mirror. GitHub and verified runtime/data evidence are authoritative.

## Repository

`Ciupanezulflipper/dividend-capture-scanner`

Primary continuity entrypoint: `AI_START_HERE.md`

## Current status

- **ENGINEERING: HOLD**
- **OPERATIONS: MONITOR**
- **STRATEGY EVALUATION: READY**

Telegram transient signal-delivery retry fix is deployed to Termux. Runtime regression result previously verified: **8/8 PASS**.

Implementation commits:

- `cfb2a2b77062c2da421e0ee53448539545a4678c`
- `140f1b7905dcc8dadfaf190c03c1d7dc24470799`

## Current delivered baseline

Runtime history now contains **27 delivered/tracked signals**.

Tracked symbols:

TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED, ESS, FRT, OMC, WTW, APD, ITW, INVH.

Persistence:

- history.json = 27
- history.json.last-good = 27
- semantic equality = true

## Latest delivery reconciliation

### Sep 15

Verified delivered HTTP 200:

- APD — 291.43, ex-date 2026-10-01, yield 2.48%, RSI 37.77
- ITW — 268.16, ex-date 2026-09-30, yield 2.57%, RSI 37.81
- INVH — 27.54, ex-date 2026-09-24, yield 4.36%, RSI 23.64

KVUE and TROW were correctly skipped as non-clean.

History advanced 24 -> 27.

Important ITW distinction:

- Sep 10 occurrence: `QUALIFIED_BUT_DELIVERY_FAILED`
- Sep 15 occurrence: successfully delivered and legitimately tracked

### Sep 16

Clean candidates:

- APD
- FRT
- INVH

All three were already tracked, so deduplication correctly prevented repeat Telegram alerts and duplicate history writes.

KVUE and LRCX were correctly skipped as non-clean.

Heartbeat delivered successfully.

The heartbeat's `Clean signals` count represents clean candidates found that day, not necessarily new post-dedup Telegram alerts.

## Evaluation contract

For each delivered signal track:

- frozen alert price
- maximum drawdown
- first +3% date and trading days
- first +5% date and trading days
- T+1/T+3/T+5/T+10/T+20 returns
- dividend-adjusted total return
- SPY return over identical dates

If +3%/+5% is not reached within T+20, record `NOT_REACHED_T20`.

## Data-quality note

EA, JNJ and ED retain stored dividend yield 0.0. Preserve the snapshots and flag them during analysis.

## Operating rule

Do not change thresholds, strategy logic, deduplication, Telegram behavior, history semantics, schema, ledger, or infrastructure unless new evidence proves a defect.

## Next step

Begin the performance study while production runs unchanged.
