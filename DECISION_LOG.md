# DECISION_LOG.md

Locked decisions. Do not reverse without explicit team agreement.

## 2026-05-01 — Repository Setup

**D1** — Dedicated private repo: `dividend-capture-scanner` / owner: Ciupanezulflipper

**D2** — Empty repo first (no auto-README/license/gitignore) to avoid first-push conflicts

**D3** — Canonical filename locked: `dividend_scanner.py` (rejected: `dividend_capture_bot.py`)

**D4** — v1 scope: scanner and alerter only. No broker. No execution. No position sizing. No exits.

**D5** — yfinance data treated as useful, not authoritative. Log missing ex-dates, never guess.

**D6** — RSI implementation: `pandas-ta` optional. Pure-pandas Wilder EWM fallback required.

**D7** — Cron timezone: `CRON_TZ=America/New_York`. Never fixed UTC.

**D8** — NYSE holidays: documented v1 limitation. Guard deferred to v1.1.

## 2026-05-01 — Termux Dependency Policy

**D9** — Core `requirements.txt` must install without native compilation.
- `lxml`: NOT core (build failure on Termux)
- `pandas-ta`: NOT core (pure-pandas fallback exists)
- `html5lib` + `beautifulsoup4`: core (pure Python, reliable)

**D10** — Optional deps (`lxml`, `pandas-ta`) are non-fatal in `run_bot.sh`. Scanner must start without them.

**D11** — Wikipedia fetch: `requests.get` with `User-Agent` -> `StringIO(response.text)` -> `pd.read_html(flavor="html5lib")`

## 2026-05-02 — Post-First-Commit

**D12** — First known-good commit: `eb5de68` on `main`. Do not rebase or force-push this ref.

**D13** — v1.1 work order is locked:
1. Telegram `.env` + delivery test
2. Full 500-ticker scan + log audit
3. NYSE holiday guard
4. CSV export
5. Secondary ex-date source

**D14** — No UI or formatting changes before data quality is validated (log audit must come first).

**D15** — RSI threshold stays at 38. Do not loosen due to signal drought. Sparse signals are expected.

**D16** — Dedup edge case (`ticker|ex_date` key does not detect company ex-date revisions) is a known
risk. Accepted for v1. Flagged for v1.1/v1.2 review — not a blocker.
