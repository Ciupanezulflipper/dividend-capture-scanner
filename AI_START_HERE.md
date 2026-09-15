# DQP — AI START HERE

Last reconciled through runtime evidence dated: 2026-09-16

## Purpose

This is the authoritative short continuity handoff for the Dividend Quality Pullback Scanner (DQP).

Repository: `Ciupanezulflipper/dividend-capture-scanner`
Runtime: Termux at `/data/data/com.termux/files/home/dividend-capture-scanner`
Default branch: `main`

GitHub plus verified runtime/data evidence are authoritative. Obsidian is a knowledge/navigation mirror and must not override GitHub/runtime evidence.

## Current production/runtime state

- Telegram transient-delivery retry fix is implemented on `main` and deployed to the Termux runtime.
- Implementation commits:
  - `cfb2a2b77062c2da421e0ee53448539545a4678c`
  - `140f1b7905dcc8dadfaf190c03c1d7dc24470799`
- Runtime head verified during the latest reconciliation: `140f1b7905dcc8dadfaf190c03c1d7dc24470799`.
- Runtime worktree was clean.
- Telegram delivery regression suite previously passed in Termux: **8/8 tests PASS**.
- Required clean-signal Telegram messages retry only on transient `transport_error` failures, with two bounded retries after short delays.
- Telegram API rejections are not retried.
- Signal history is committed only after verified successful Telegram delivery.
- `history.json` and `history.json.last-good` remain the runtime persistence pair.

## Sep 10 ITW incident

On the 2026-09-10 scheduled scan:

- Universe scanned: 503.
- ITW qualified as the one clean signal.
- ITW signal snapshot: price ~268.69, MA200 ~264.88, RSI14 ~34.3, dividend yield ~2.56%, ex-date 2026-09-30.
- Telegram signal delivery failed with a transient connection reset.
- The heartbeat delivered successfully seconds later.
- `history.json` was intentionally not modified because ITW delivery was not verified.

Classification of that occurrence: **QUALIFIED_BUT_DELIVERY_FAILED**.

This incident justified the bounded transport retry fix. No strategy thresholds were changed.

## Sep 11 live validation

The next live run delivered four clean signals successfully:

- ESS
- FRT
- OMC
- WTW

Runtime reconciliation proved:

- all four had `attempted=true`, `delivered=true`, `outcome=delivered`, HTTP 200;
- `history.json` advanced **20 -> 24**;
- `history.json` and `history.json.last-good` were semantically equal;
- no delivered signal was missing from history;
- no failed signal was incorrectly written.

The same run's heartbeat timed out after the four signal deliveries succeeded. Run-level failure reporting was truthful and did not represent signal loss.

## Sep 15 live reconciliation

Three new clean signals were successfully delivered and written:

| Symbol | Runtime alerted_at UTC | Price | Ex-date | Yield % | RSI |
|---|---|---:|---|---:|---:|
| APD | 2026-09-14T14:18:03.977664+00:00 | 291.43 | 2026-10-01 | 2.4843 | 37.77 |
| ITW | 2026-09-14T14:18:04.706713+00:00 | 268.16 | 2026-09-30 | 2.5656 | 37.81 |
| INVH | 2026-09-14T14:18:05.560913+00:00 | 27.54 | 2026-09-24 | 4.3573 | 23.64 |

Structured Telegram evidence:

- APD: delivered=true, outcome=delivered, HTTP 200
- ITW: delivered=true, outcome=delivered, HTTP 200
- INVH: delivered=true, outcome=delivered, HTTP 200
- heartbeat: delivered=true, HTTP 200

KVUE and TROW were correctly skipped as `telegram_clean_only_non_clean_signal`.

History advanced exactly **24 -> 27**.

Primary/backup persistence check:

- `PRIMARY_LASTGOOD_EQUAL = true`
- `PRIMARY_COUNT = 27`
- `LASTGOOD_COUNT = 27`

Important ITW distinction:

- Sep 10 ITW occurrence remains a documented `QUALIFIED_BUT_DELIVERY_FAILED` event.
- Sep 15 ITW was a later valid occurrence, successfully delivered and legitimately written to history.
- Do not collapse the failed Sep 10 occurrence and successful Sep 15 occurrence into one delivery event.

## Sep 16 deduplication proof

Sep 16 `signal_passed=true` rows were:

- APD — HIGH / clean
- FRT — HIGH / clean
- INVH — HIGH / clean
- KVUE — LOW / too close to ex-date
- LRCX — LOW / low-yield + abnormal-drop warning

The clean candidates APD, FRT and INVH were already in history, so no duplicate Telegram signal was sent.

KVUE and LRCX were correctly skipped by the clean-only gate.

The heartbeat delivered successfully with HTTP 200.

Therefore Sep 16 behavior is correct:

- clean candidates: 3
- new clean events: 0
- signal sends: 0
- duplicate sends: 0
- new history writes: 0
- heartbeat: delivered

The heartbeat label `Clean signals` means clean candidates found by that day's scan, not necessarily new Telegram alerts after deduplication.

## Frozen delivered-signal baseline

Current runtime delivered/tracked history count: **27**.

Stored schema:

`alerted_at, days_away, dividend_yield_pct, ex_date, ma, price, rsi, symbol`

Current tracked symbols:

`TGT, TRV, WMB, AEE, PCAR, EA, CB, JNJ, NEE, PSA, DVN, BALL, APA, TPL, EOG, REG, TJX, FCX, HUBB, ED, ESS, FRT, OMC, WTW, APD, ITW, INVH`

Data-quality note: EA, JNJ and ED have stored `dividend_yield_pct=0.0`. Preserve those historical snapshots as-is and flag them during analysis; do not rewrite history silently.

## Strategy evaluation contract — LOCKED

For every delivered signal, evaluate from the frozen signal price:

1. maximum drawdown after alert;
2. first date price reaches +3% and trading days elapsed;
3. first date price reaches +5% and trading days elapsed;
4. T+1, T+3, T+5, T+10 and T+20 returns;
5. dividend-adjusted total return where applicable;
6. SPY return over identical holding dates.

If +3%/+5% is not reached within 20 trading days, record `NOT_REACHED_T20`.

Portfolio-level metrics:

- +3% hit rate within T+20;
- +5% hit rate within T+20;
- median trading days to +3%/+5%;
- median and worst maximum drawdown;
- T+20 win rate;
- median T+20 total return;
- SPY-relative performance.

## Current operating decision

**ENGINEERING: HOLD**

**OPERATIONS: MONITOR**

**STRATEGY EVALUATION: READY**

No repository or strategy fix is justified by the Sep 15/16 evidence.

Do not change:

- RSI threshold;
- MA200 logic;
- yield/ex-date rules;
- deduplication;
- Telegram retry behavior;
- history persistence semantics;
- ledger/schema work.

## Next high-value task

Begin the performance study on the frozen delivered history while production continues unchanged.

Track prospective/current cases normally, including APD, ITW and INVH.

Keep the Sep 10 ITW failed-delivery occurrence as a separate operational incident in audit history.

## Starting a new chat

A new DQP chat should:

1. read this file first;
2. inspect current GitHub `main`;
3. inspect current Termux runtime evidence before changing anything;
4. preserve the **27-signal** delivered baseline;
5. preserve the distinction between Sep 10 failed ITW delivery and Sep 15 successful ITW delivery;
6. avoid strategy changes until the performance study provides evidence.

Never assume a GitHub implementation is deployed until runtime proves it.
