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

## Latest verified state — 2026-09-12

### Telegram retry correction remains deployed

The transient Telegram transport retry fix is deployed at runtime head `140f1b7905dcc8dadfaf190c03c1d7dc24470799`.

Behavior:
- required clean-signal messages retry transient `transport_error` failures only;
- up to two bounded retries after short delays;
- API rejection is not retried;
- history is written only after verified signal delivery.

Termux regression suite: **8/8 PASS**.

### Sep 11 live reconciliation

The next live run delivered four clean signals successfully:

`ESS, FRT, OMC, WTW`

Runtime evidence:
- signal attempt count = 4
- signal success count = 4
- signal failure count = 0
- each signal returned HTTP 200 and `outcome=delivered`
- `history.json` count advanced **20 -> 24**
- `history.json` and `history.json.last-good` are semantically equal
- delivered-but-not-history = empty
- invalid history writes = empty
- ITW remains excluded as `QUALIFIED_BUT_DELIVERY_FAILED`

New stored snapshots:

| Symbol | Alerted at UTC | Price | Ex-date | Yield % | RSI | MA200 |
|---|---|---:|---|---:|---:|---:|
| ESS | 2026-09-10T14:40:46.599791+00:00 | 274.37 | 2026-09-30 | 3.776 | 36.07 | 263.999 |
| FRT | 2026-09-10T14:40:48.533577+00:00 | 115.16 | 2026-10-01 | 4.029 | 34.30 | 109.986 |
| OMC | 2026-09-10T14:40:49.966731+00:00 | 78.30 | 2026-09-18 | 4.087 | 35.88 | 77.189 |
| WTW | 2026-09-10T14:40:51.298522+00:00 | 313.72 | 2026-09-30 | 1.224 | 37.96 | 298.864 |

The run-level status was still `success=false` / exit 23 because the heartbeat transport timed out after the four signal deliveries succeeded. This is truthful runtime health reporting, not signal loss.

### Delivered baseline

Current delivered/tracked history count: **24**.

Symbols:

`TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED, ESS, FRT, OMC, WTW`

EA, JNJ and ED retain stored yield `0.0`; preserve as historical snapshots and flag during analysis.

### Evaluation contract

For every delivered signal, use the frozen alert price and track:

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

Do not change strategy thresholds, filters, schema, ledger design, or infrastructure unless fresh evidence proves a defect.

## Current next step

Run the mature-signal performance study while production continues unchanged.

Prospective/current cases:
- PSA
- ESS
- FRT
- OMC
- WTW

Separate non-delivered case:
- ITW — `QUALIFIED_BUT_DELIVERY_FAILED`

## Durable records

- `AI_START_HERE.md` — authoritative current handoff
- `CONTINUITY.md` — continuity summary
- `DECISION_LOG.md` — historical locked decisions
- `docs/DECISION_2026-09-10_RUNTIME_AND_EVALUATION.md`
- `docs/INCIDENT_2026-09-10_ITW_TELEGRAM_TRANSPORT.md`
- `obsidian/30_Dividend-Scanner/Current-State.md`

## Historical context

Earlier implementation decisions, first live signals, v1.1 audit/report work, heartbeat introduction, stale ex-date findings, and restore points remain documented in `DECISION_LOG.md` and repository history. Do not infer current state from old dated sections without checking this file and `AI_START_HERE.md` first.
