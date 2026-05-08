# DECISION_LOG.md

Locked decisions. Do not reverse without explicit team agreement.

## 2026-05-01 — Repository Setup

**D1** Dedicated private repo: `dividend-capture-scanner` / Ciupanezulflipper

**D2** Empty repo first — no auto-README/license/gitignore

**D3** Canonical filename locked: `dividend_scanner.py`

**D4** v1 scope: scanner and alerter only. No broker. No execution. No sizing. No exits.

**D5** yfinance = useful, not authoritative. Log missing/stale ex-dates. Never guess.

**D6** RSI: `pandas-ta` optional. Pure-pandas Wilder EWM fallback required.

**D7** Cron: `CRON_TZ=America/New_York`. Never fixed UTC.

**D8** NYSE holidays: documented v1 limitation. Guard deferred until after audit.

## 2026-05-01 — Termux Dependency Policy

**D9** Core `requirements.txt` must install without native compilation.
- `lxml`: NOT core (Termux build failure)
- `pandas-ta`: NOT core (pure-pandas fallback exists)
- `html5lib` + `beautifulsoup4`: core (pure Python, reliable)

**D10** Optional deps (`lxml`, `pandas-ta`) are non-fatal in `run_bot.sh`.

**D11** Wikipedia fetch: `requests.get` + `User-Agent` → `StringIO` → `pd.read_html(flavor="html5lib")`

## 2026-05-02 — Post-First-Commit

**D12** First known-good commit: `eb5de68`. Do not rebase or force-push this ref.

**D13** v1.1 work order (updated 2026-05-09):
1. ~~Telegram `.env` + delivery test~~ DONE
2. ~~CSV export / report mode~~ DONE — PR #1
3. ~~Reason-count audit output~~ DONE — PR #1
4. Full 500-ticker scan + report review — PENDING
5. Post-signal tracking skeleton
6. NYSE holiday guard (after audit)
7. Secondary ex-date source (after audit)

**D14** No UI or cosmetic dashboard changes before data quality is validated.
The only accepted display change in v1.1 was audit visibility needed for measurement.

**D15** RSI threshold stays at 38. Sparse signals are expected. Do not loosen.

**D16** Dedup edge case (`ticker|ex_date` key misses ex-date revisions) — accepted for v1, flagged v1.2.

## 2026-05-02 — Thesis Reframe

**D17** Project direction: **Dividend Quality Pullback Scanner**
File and repo names unchanged for now — rename deferred, conscious tech debt.

**D18** Ex-dividend date is a timing context filter, not the primary trading thesis.

**D19** Alerts are candidate research prompts. Manual validation required before any trade.

**D20** Performance tracking mandatory: 1/3/5/10/20 trading day returns vs SPY.
Track: win rate, avg return, max drawdown, outperformance, signal quality by sector.

**D21** This is a hypothesis-testing and stock discovery tool, not a passive-income machine.

**D22** Deferred until after full audit: NYSE holiday guard, secondary ex-date source,
dashboard polish, threading, any broker automation.

## 2026-05-03 — Post-Telegram and First Live Run

**D23** Telegram delivery test: DONE/PASS. Bot: @DividendQualityBot.
No Telegram token or chat ID recorded in any committed file.

**D24** Weekend guard validated: exits cleanly without `--force-weekend`. Correct behaviour.

**D25** history.json empty-state creation on a live no-signal run is expected behaviour.
Not a blocker. File is git-ignored.

**D26** yfinance stale ex-date problem is now PROVEN, not hypothetical.
- ADBE: returned 2005-03-24 (21 years stale)
- AMD: returned 1995-04-27 (31 years stale)
Full scan reason-count audit is the immediate priority to quantify failure rate.

**D27** Repo rename deferred as conscious, documented tech debt.
Will revisit after v1.1 audit is complete. No urgency.

## 2026-05-07 — First Real Telegram Signals

**D28** Live Telegram alert path is proven. Three real alerts fired on 2026-05-07:
- ED — signal price 106.87, ex-date 2026-05-13, 5 days away, RSI 37.6
- EA — signal price 200.79, ex-date 2026-05-27, 19 days away, RSI 35.1
- JNJ — signal price 224.62, ex-date 2026-05-26, 18 days away, RSI 37.1

**D29** EA exposed a likely low-yield noise problem. Do not hard-filter immediately.
Measure candidate minimum dividend yield first. Initial audit candidate: 1.0%.

**D30** ED exposed a likely too-close-to-ex-date timing problem. Do not hard-filter immediately.
Measure candidate minimum days-to-ex-date first. Initial audit candidate: 7 days.

**D31** JNJ is the cleanest early example of the intended thesis fit.

## 2026-05-09 — v1.1 Audit/Report Merge

**D32** PR #1 merged v1.1 audit/report layer into `main`.
Merged main commit: `f2949d42c286720d20a90710f6e6a1bde8a7c8cd`.

**D33** v1.1 adds CSV audit/report output:
`reports/scan_report_YYYY-MM-DD.csv`.
Reports are runtime artifacts and remain ignored by git.

**D34** v1.1 adds structured reason categories:
- `no_ex_date_available`
- `stale_or_past_ex_date`
- `ex_date_outside_window`
- `yfinance_error`
- `technical_failed_rsi`
- `technical_failed_ma200`
- `signal_generated`

**D35** v1.1 adds audit flags:
- `valid_forward_ex_date_in_window`
- `low_yield_candidate`
- `ex_date_too_close_candidate`

**D36** v1.1 adds audit-only proposed filters:
- `--audit-min-yield`, default `1.0`
- `--audit-min-days-to-ex-date`, default `7`

**D37** These are NOT hard strategy filters yet. Current signal generation remains:
ex-date within 21 days + RSI(14) < 38 + price > MA(200).
Hard activation requires full 500-ticker audit evidence.

**D38** Telegram alert header changed from `Dividend Capture Signal` to
`Dividend Quality Pullback Signal`.

**D39** Restore points exist before v1.1 work, after v1.1 branch validation,
and after merged-main validation. See `CONTINUITY.md` for exact refs.
