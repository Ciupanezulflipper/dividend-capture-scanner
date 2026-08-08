# CONTINUITY.md

## Project
Dividend Quality Pullback Scanner
(Repo still named `dividend-capture-scanner` — rename deferred, conscious tech debt)
(File still named `dividend_scanner.py` — rename deferred to v1.2)

## Repository
- Owner: Ciupanezulflipper
- Repo: dividend-capture-scanner
- Visibility: private
- Remote: git@github.com:Ciupanezulflipper/dividend-capture-scanner.git
- Local (Termux): /data/data/com.termux/files/home/dividend-capture-scanner

## Shared Android/Termux Engineering Baseline — 2026-08-08
- Read `ANDROID_TERMUX_TOOLCHAIN.md` before proposing or installing additional phone tooling.
- It records the verified shared Android/Termux toolchain used across this scanner, BotA, and LifVio.
- Global tool availability does not mean hooks, formatters, scanners, or Spec Kit configuration are enabled in this repository.

## Known Commits (verify with git log before assuming state)
| Hash | Description |
|---|---|
| eb5de68 | Initial dividend capture scanner |
| 04ff0ea | docs: update control files after first commit and v1.1 planning |
| 2c1c7c6 | docs: record Telegram DONE, weekend guard PASS, stale ex-date proven, v1.1 audit next |
| 443af51 | feat: add v1.1 audit report layer — validated on branch before merge |
| f2949d4 | feat: add v1.1 audit report layer — merged into main via PR #1 |

Run `git log --oneline -5` to confirm actual pushed state before starting any session.

## Current Verified State — 2026-06-15
| Item | Status |
|---|---|
| GitHub repo created | YES |
| First commit pushed | YES — eb5de68 |
| Current main commit | see `git log --oneline -1` |
| Branch | main |
| Python syntax check | PASS |
| Bash syntax check | PASS |
| Termux dry-run smoke test | PASS |
| Telegram bot created | YES — @DividendQualityBot |
| Telegram token verified (getMe) | PASS |
| Telegram chat ID extracted | PASS |
| Telegram sendMessage test | PASS |
| .env ignored by git | PASS |
| No secrets committed | YES |
| Weekend guard triggered correctly | PASS |
| Forced-weekend limited scan (10 tickers) | PASS — 0 signals |
| history.json created on live no-signal run | YES — empty state, ignored by git |
| v1.1 audit/report layer | MERGED into main — PR #1 |
| CSV report output | IMPLEMENTED — `reports/scan_report_YYYY-MM-DD.csv` |
| Reason-count summary | IMPLEMENTED |
| Audit-only min dividend yield flag | IMPLEMENTED — default 1.0% |
| Audit-only min days-to-ex-date flag | IMPLEMENTED — default 7 days |
| Hard min-yield filter | NOT ACTIVATED |
| Hard min-days-to-ex-date filter | NOT ACTIVATED |
| Full 500-ticker scan + audit | RUNNING — 503 tickers, daily at 10 AM ET |
| --daily-heartbeat flag | IMPLEMENTED — opt-in, wired into cron |
| Live 0-signal heartbeat delivery | PROVEN — 2026-06-15 |

## 13-Day Telegram Silence Diagnosis — 2026-06-15
Silence period: 2026-06-02 → 2026-06-15. No signals fired.

Root cause: **not a bug**. Scanner ran correctly on June 11 and June 12 (confirmed
via `cron_dividend_bot.log`). Scanned all 503 tickers. Found 0 clean signals
— no ticker cleared RSI(14) < 38 + price > MA(200) + ex-date in 21-day window
simultaneously. Market gave nothing; silence was correct discipline.

Problem: correct silence is indistinguishable from a dead bot.
Fix: `--daily-heartbeat` flag (see below).

## Daily Heartbeat Feature — 2026-06-15
- New flag `--daily-heartbeat` (store_true, default OFF) added to `dividend_scanner.py`
- When set + not dry-run + token/chat_id present: sends ONE Telegram after the scan via existing `send_telegram()`
- Format: `DQP heartbeat YYYY-MM-DD | scanned N | X clean signal(s) | top skip: <reason> <count>`
- Fires regardless of signal count — proves alive on 0-signal days
- Intentionally SKIPPED on collapse path: collapse already sends a `DATA_PROVIDER_FAILURE` admin alert
- Known limitation: proves healthy-run completion only. A crash before scan completes produces no heartbeat and no alert. Acceptable — external watchdog would be over-engineering for a research scanner.
- Known cosmetic bug PENDING: Telegram strips underscores in heartbeat text (rendered `staleorpastexdate` instead of `stale_or_past_ex_date`). Markdown `parse_mode` issue in `send_telegram()`. Not yet fixed.
- Wired into the 10 AM ET cron job. Fixed a fused-flag spacing bug during wiring.
- Proved live on a 0-signal run: heartbeat landed on phone 2026-06-15.

## Thesis
**Dividend Quality Pullback Scanner**
Ex-dividend date = timing context and catalyst filter.
Primary signal = quality dividend stock in a controlled pullback while
the 200D MA trend is intact.
Alerts are candidate research prompts, not buy commands.

## Locked Decisions
- Canonical Python file: `dividend_scanner.py` (rename deferred)
- Product direction: Dividend Quality Pullback Scanner
- v1 scope: scanner/alerter only — no execution
- Signals require manual validation before acting
- Dedup key: `ticker|ex_date`
- RSI threshold: 38 — do not loosen out of impatience
- Repo rename: deferred until after v1.1 audit
- Minimum dividend yield and minimum days-to-ex-date are audit-only until full scan data supports activation

## Proven Data-Quality Issue
Log evidence from forced-weekend 10-ticker run confirms yfinance stale ex-date
problem is real, not hypothetical:
- ADBE: returned ex_date 2005-03-24 (21 years stale)
- AMD: returned ex_date 1995-04-27 (31 years stale)
Multiple first-10 tickers returned past/stale ex-dates outside the 21-day window.
This is a known yfinance limitation. Full scan audit will quantify the failure rate.

## First Real Telegram Signals — 2026-05-07
Three real alerts fired, proving the live Telegram path works.

| Ticker | Signal Price | Ex-Date | Days Away | RSI(14) | Observation |
|---|---:|---|---:|---:|---|
| ED | 106.87 | 2026-05-13 | 5 | 37.6 | Dividend-quality candidate, but ex-date likely too close |
| EA | 200.79 | 2026-05-27 | 19 | 35.1 | Technical pass but low-yield/noisy dividend candidate |
| JNJ | 224.62 | 2026-05-26 | 18 | 37.1 | Best thesis-fit example |

Findings from these alerts:
- Old Telegram header still said `Dividend Capture Signal`; v1.1 corrected this to `Dividend Quality Pullback Signal`.
- EA exposed the need to measure a minimum dividend-yield filter.
- ED exposed the need to measure a minimum days-to-ex-date filter.
- JNJ is the cleanest example of the intended thesis.

## v1.1 Audit/Report Layer — Merged 2026-05-09
PR #1 merged the audit/report layer into `main`.

Validated locally on Termux before and after merge:
- `python3 -m py_compile dividend_scanner.py` — PASS
- `bash -n run_bot.sh` — PASS
- `./run_bot.sh --dry-run --limit 10 --show-all --force-weekend` — PASS
- CSV report created — PASS
- git status clean after runtime test — PASS

v1.1 added:
- Telegram header rename to `Dividend Quality Pullback Signal`
- Dividend yield visibility in scan rows and Telegram alerts
- CSV report output: `reports/scan_report_YYYY-MM-DD.csv`
- Reason-count summary
- Structured reason categories
- Audit-only proposed filters:
  - `--audit-min-yield`, default `1.0`
  - `--audit-min-days-to-ex-date`, default `7`

Important: these are not hard filters yet. The scanner still generates signals using the original signal logic:
`ex-date in 21-day window + RSI(14) < 38 + price > MA(200)`.

## Restore Points
| Restore Point | Type | Ref | Commit |
|---|---|---|---|
| Before v1.1 audit work | Tag | `restore-before-v1.1-audit-20260509-161817` | 2c1c7c6 |
| Before v1.1 audit work | Branch | `restore/main-before-v1.1-audit-20260509-161817` | 2c1c7c6 |
| After v1.1 branch validation | Tag | `restore-v1.1-audit-validated-20260509-162856` | 443af51 |
| After v1.1 branch validation | Branch | `restore/v1.1-audit-validated-20260509-162856` | 443af51 |
| After v1.1 merge/main validation | Tag | `restore-main-after-v1.1-merge-20260509-164328` | f2949d4 |
| After v1.1 merge/main validation | Branch | `restore/main-after-v1.1-merge-20260509-164328` | f2949d4 |

## Validated Run History
| Date | Command | Result |
|---|---|---|
| 2026-05-01 | `./run_bot.sh --dry-run --limit 10 --show-all` | PASS |
| 2026-05-03 | `./run_bot.sh --limit 10 --show-all` | Weekend guard triggered correctly |
| 2026-05-03 | `./run_bot.sh --limit 10 --show-all --force-weekend` | PASS — 0 signals, history.json created empty |
| 2026-05-09 | `./run_bot.sh --dry-run --limit 10 --show-all --force-weekend` on v1.1 branch | PASS — CSV report created |
| 2026-05-09 | `./run_bot.sh --dry-run --limit 10 --show-all --force-weekend` on merged main | PASS — CSV report created |

## Signal Drought Watch — 2026-06-15
Near-zero clean signals since 2026-06-02. Only ~17 resolved signals total vs the
50–100 threshold agreed before any RSI/MA200 strategy change. Too early to judge
whether filters are too tight for an uptrending regime. **No strategy changes yet.**
Watch for: prolonged drought (correct discipline) vs filters miscalibrated for
a low-volatility, uptrending market. Revisit when resolved signal count reaches 50.

## Current Next Step
1. Accumulate resolved signals to 50–100 (audit tool now wired; heartbeat confirms daily health).
2. Review CSV reports and audit signal performance tool output.
3. Decide whether to activate hard filters once data supports it:
   - Candidate minimum dividend yield: 1.0%
   - Candidate minimum days-to-ex-date: 7 days
4. Fix underscores-stripped cosmetic bug in `send_telegram()` (Markdown parse_mode).

## v1.1 Sequencing — Updated
1. ~~Telegram `.env` setup + delivery test~~ **DONE**
2. ~~CSV export / report mode~~ **DONE — PR #1**
3. ~~Reason-count audit output~~ **DONE — PR #1**
4. Full 500-ticker scan + report review — **PENDING**
5. Post-signal tracking skeleton
6. NYSE holiday guard (after audit confirms it matters)
7. Secondary ex-date source (after audit quantifies yfinance failure rate)

## Deferred
- Dashboard / UI polish
- Threading / async optimisation
- Any broker or trading automation
- Repo rename (conscious tech debt)
- Hard min-yield filter until audit data supports it
- Hard min-days-to-ex-date filter until audit data supports it

## Known Edge Cases
- `history.json` dedup key does not detect company ex-date revisions — v1.2 item
- yfinance stale ex-date coverage now proven — failure rate to be measured in full scan
- Narrow Termux screen makes Rich table columns wrap aggressively; CSV report is the source of truth

## Success Metrics to Track
- % of S&P 500 with usable forward ex-date data
- Signals generated per month
- Average return at 1/3/5/10/20 trading days post-signal
- Win rate post-signal
- Max drawdown post-signal
- Outperformance vs SPY on same signal dates
- Signal quality by sector
