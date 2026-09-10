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
Repository visibility verified 2026-09-10: **public**.
Termux runtime: `/data/data/com.termux/files/home/dividend-capture-scanner`

## Latest verified state — 2026-09-10

### Telegram reliability correction

The Sep 10 run produced one clean ITW signal. Telegram signal delivery was attempted and failed with a transient `ConnectionResetError(104, 'Connection reset by peer')`. Roughly five seconds later the daily heartbeat delivered successfully with HTTP 200.

This proved a narrow delivery-control defect: a valid clean signal could be lost on a transient Telegram transport failure even when connectivity recovered seconds later.

ITW was correctly **not** added to `history.json` because delivery was not verified.

Classification: `QUALIFIED_BUT_DELIVERY_FAILED`.

Correction implemented on `main`:
- `cfb2a2b77062c2da421e0ee53448539545a4678c`
- `140f1b7905dcc8dadfaf190c03c1d7dc24470799`

Behavior now:
- required clean-signal messages retry transient `transport_error` failures only;
- up to two bounded retries after short delays;
- stop immediately on verified success;
- Telegram API rejection is not retried;
- heartbeat behavior is unchanged;
- history remains committed only after verified successful signal delivery.

Termux was fast-forwarded from `abde4ee` to `140f1b7` and `tests.test_telegram_delivery` passed **8/8**.

See `docs/INCIDENT_2026-09-10_ITW_TELEGRAM_TRANSPORT.md`.

### Frozen delivered-signal baseline

Runtime `history.json` currently contains **20 delivered/tracked signals** using schema:

`alerted_at, days_away, dividend_yield_pct, ex_date, ma, price, rsi, symbol`

Symbols:

`TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED`

PSA is the newest delivered forward-validation case. ITW is not part of delivered history.

EA, JNJ and ED contain stored `dividend_yield_pct=0.0`. Preserve those historical snapshots as-is and flag them as data-quality limitations during analysis; do not silently rewrite history.

Current retained structured Telegram logs prove PSA delivery and show no `DELIVERED_BUT_NOT_HISTORY` mismatch. Older history entries predate retained structured Telegram delivery logs, so absence from the current log is not evidence that they were never delivered.

Full baseline details are in `AI_START_HERE.md`.

## Locked strategy evaluation contract — 2026-09-10

For every delivered signal, evaluate from the frozen alert price:

1. maximum drawdown after alert;
2. first date price reaches +3% and trading days elapsed;
3. first date price reaches +5% and trading days elapsed;
4. T+1, T+3, T+5, T+10 and T+20 returns;
5. dividend-adjusted total return where applicable;
6. SPY return over identical dates.

If +3% or +5% is not reached within 20 trading days, record `NOT_REACHED_T20`.

Portfolio metrics:
- +3% hit rate within T+20;
- +5% hit rate within T+20;
- median trading days to +3%/+5%;
- median and worst maximum drawdown;
- T+20 win rate;
- median T+20 total return;
- outperformance versus SPY.

19 of the 20 delivered signals are mature enough for T+20 analysis. PSA remains prospective.

See `docs/DECISION_2026-09-10_RUNTIME_AND_EVALUATION.md`.

## Current operating decision

**ENGINEERING: HOLD**

**OPERATIONS: MONITOR**

**STRATEGY EVALUATION: READY**

For the next 3–5 trading days, do not change strategy thresholds, filters, schema, ledger design, or infrastructure unless new evidence proves a defect.

Verify only:
1. weekday 10:00 New York scheduled run executes;
2. if a clean signal exists, it is delivered before/with the heartbeat;
3. verified delivered signals enter `history.json`; failed deliveries do not.

Low signal frequency alone is not a reason to loosen RSI or other thresholds.

## Current next step

Run the mature 19-case performance study under the locked evaluation contract while production continues unchanged. Keep PSA prospective. Keep ITW separately classified as `QUALIFIED_BUT_DELIVERY_FAILED` rather than inserting it retroactively into delivered history.

## Durable records

- `AI_START_HERE.md` — current authoritative continuity handoff
- `CONTINUITY.md` — current project continuity
- `DECISION_LOG.md` — historical locked decisions
- `docs/DECISION_2026-09-10_RUNTIME_AND_EVALUATION.md` — latest runtime/evaluation decision
- `docs/INCIDENT_2026-09-10_ITW_TELEGRAM_TRANSPORT.md` — ITW delivery incident and correction
- `obsidian/30_Dividend-Scanner/Current-State.md` — Obsidian-ready mirror

## Historical context

Earlier implementation decisions, first live signals, v1.1 audit/report work, heartbeat introduction, stale ex-date findings, and restore points remain documented in `DECISION_LOG.md` and repository history. Do not infer current state from old dated sections without checking this file and `AI_START_HERE.md` first.
