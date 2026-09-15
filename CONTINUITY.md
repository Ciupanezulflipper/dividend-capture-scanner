# CONTINUITY.md

## Project
Dividend Quality Pullback Scanner (DQP)

Repo name remains `dividend-capture-scanner`; canonical scanner file remains `dividend_scanner.py`.

## Authority and startup order

1. Read `AI_START_HERE.md` first.
2. Inspect current GitHub `main`.
3. Verify Termux runtime evidence before assuming GitHub changes are deployed.
4. Use `DECISION_LOG.md` and dated docs for historical rationale.

GitHub plus verified runtime/data evidence are authoritative. Obsidian is a knowledge/navigation mirror and must not override runtime facts.

Repository: `Ciupanezulflipper/dividend-capture-scanner`
Default branch: `main`
Termux runtime: `/data/data/com.termux/files/home/dividend-capture-scanner`

## Latest verified state

### Telegram retry correction

The transient Telegram transport retry fix remains deployed at runtime head:

`140f1b7905dcc8dadfaf190c03c1d7dc24470799`

Behavior:

- retry required clean-signal `transport_error` failures only;
- at most two bounded retries;
- do not retry API rejection;
- write history only after verified successful signal delivery.

### Delivered baseline progression

Verified history progression:

- prior baseline: 20
- Sep 11: +ESS +FRT +OMC +WTW -> 24
- Sep 15: +APD +ITW +INVH -> 27
- Sep 16: 0 new writes because APD/FRT/INVH were already tracked

Current delivered/tracked history count: **27**.

Current tracked symbols:

`TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED, ESS, FRT, OMC, WTW, APD, ITW, INVH`

Runtime persistence check:

- `history.json = 27`
- `history.json.last-good = 27`
- semantic equality = true

### Sep 15 delivery proof

Delivered successfully with HTTP 200:

- APD
- ITW
- INVH

KVUE and TROW were correctly skipped by the clean-only gate.

History saved with 27 entries.

The Sep 15 ITW event is a valid later signal and must remain in delivered history.

The earlier Sep 10 ITW occurrence remains separately documented as `QUALIFIED_BUT_DELIVERY_FAILED`.

### Sep 16 deduplication proof

Sep 16 clean candidates:

- APD
- FRT
- INVH

All three were already recorded, so no duplicate signal alert was sent and no new history row was added.

Non-clean passed rows:

- KVUE
- LRCX

Both were correctly skipped.

Heartbeat delivered HTTP 200.

This proves the intended chain:

`daily candidate -> clean gate -> dedup -> Telegram only for new clean event -> history only after verified delivery`

### Data-quality note

EA, JNJ and ED retain stored `dividend_yield_pct=0.0`. Preserve the historical snapshot and flag during analysis.

## Locked evaluation contract

For every delivered signal track:

1. maximum drawdown;
2. first +3% hit date and trading days;
3. first +5% hit date and trading days;
4. T+1/T+3/T+5/T+10/T+20 returns;
5. dividend-adjusted total return;
6. SPY return over identical dates.

If +3%/+5% is not reached within T+20, record `NOT_REACHED_T20`.

Portfolio metrics:

- +3% hit rate within T+20
- +5% hit rate within T+20
- median days to target
- median/worst drawdown
- T+20 win rate
- median T+20 total return
- SPY-relative performance

## Current operating decision

**ENGINEERING: HOLD**

**OPERATIONS: MONITOR**

**STRATEGY EVALUATION: READY**

No strategy or repository change is justified by the latest evidence.

## Current next step

Run the performance study while production continues unchanged.

Do not modify thresholds, deduplication, Telegram delivery behavior, history semantics, or ledger/schema design unless new evidence proves a defect.

## Durable records

- `AI_START_HERE.md`
- `CONTINUITY.md`
- `DECISION_LOG.md`
- `docs/DECISION_2026-09-10_RUNTIME_AND_EVALUATION.md`
- `docs/INCIDENT_2026-09-10_ITW_TELEGRAM_TRANSPORT.md`
- `obsidian/30_Dividend-Scanner/Current-State.md`
