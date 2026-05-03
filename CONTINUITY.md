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

## Known Commits (verify with git log before assuming state)
| Hash | Description |
|---|---|
| eb5de68 | Initial dividend capture scanner |
| 04ff0ea | docs: update control files after first commit and v1.1 planning |
| (thesis reframe commit) | docs: thesis reframe to Dividend Quality Pullback Scanner |

Run `git log --oneline -5` to confirm actual pushed state before starting any session.

## Current Verified State — 2026-05-03
| Item | Status |
|---|---|
| GitHub repo created | YES |
| First commit pushed | YES — eb5de68 |
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
| **Full 500-ticker scan + log audit** | **PENDING** |

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

## Proven Data-Quality Issue
Log evidence from forced-weekend 10-ticker run confirms yfinance stale ex-date
problem is real, not hypothetical:
- ADBE: returned ex_date 2005-03-24 (21 years stale)
- AMD: returned ex_date 1995-04-27 (31 years stale)
Multiple first-10 tickers returned past/stale ex-dates outside the 21-day window.
This is a known yfinance limitation. Full scan audit will quantify the failure rate.

## Validated Run History
| Date | Command | Result |
|---|---|---|
| 2026-05-01 | `./run_bot.sh --dry-run --limit 10 --show-all` | PASS |
| 2026-05-03 | `./run_bot.sh --limit 10 --show-all` | Weekend guard triggered correctly |
| 2026-05-03 | `./run_bot.sh --limit 10 --show-all --force-weekend` | PASS — 0 signals, history.json created empty |

## v1.1 Sequencing (locked order)
1. ~~Telegram `.env` setup + delivery test~~ **DONE**
2. Full 500-ticker scan + reason-count audit
3. CSV export / report mode
4. Post-signal tracking skeleton
5. NYSE holiday guard (after audit confirms it matters)
6. Secondary ex-date source (after audit quantifies yfinance failure rate)

## Deferred
- Dashboard / UI polish
- Threading / async optimisation
- Any broker or trading automation
- Repo rename (conscious tech debt)

## Known Edge Cases
- `history.json` dedup key does not detect company ex-date revisions — v1.2 item
- yfinance stale ex-date coverage now proven — failure rate to be measured in full scan

## Success Metrics to Track
- % of S&P 500 with usable forward ex-date data
- Signals generated per month
- Average return at 1/3/5/10/20 trading days post-signal
- Win rate post-signal
- Max drawdown post-signal
- Outperformance vs SPY on same signal dates
- Signal quality by sector
