# STRATEGY_HISTORY.md

## Thesis History

### v0 — Original Framing (deprecated)
"Dividend capture scanner" — buy before ex-date, capture yield.
**Problem:** price typically adjusts downward by the dividend amount on ex-date.
Capturing the yield alone is not a reliable edge.

### v1 — Current Framing (2026-05-02)
**Dividend Quality Pullback Scanner**
Ex-dividend date = timing context and catalyst filter only.
Signal = quality dividend stock in a controlled pullback, 200D MA trend intact.
Upcoming ex-date focuses attention. RSI + MA is the actual condition.

## v1 Technical Implementation

### Universe
- Dynamically fetch S&P 500 from Wikipedia each run (currently 503 tickers)
- `requests.get` with `User-Agent` → `StringIO` → `pd.read_html(flavor="html5lib")`

### Filters (all required)
| Filter | Condition |
|---|---|
| Ex-dividend date | Within next 21 calendar days |
| RSI(14) | Below 38 |
| Price vs trend | Current price above 200-day MA |

### RSI Engine
- Primary (optional): `pandas-ta` if installed
- Fallback (always present): pure-pandas Wilder EWM

### Signal Output
```
BUY SIGNAL: [Ticker] | Yield: [X]% | RSI: [X] | Ex-Date: [Date]
```
Alerts are candidate research prompts. Not buy commands.

### State Management
- `history.json`: dedup by `ticker|ex_date` — never committed
- `--dry-run`: must never write `history.json` or send Telegram
- Empty-state `history.json` created on first live no-signal run — expected, git-ignored

### Logging
Per-ticker: start / skip-reason / duplicate / error / alert — never committed

## v1 Known Limitations
- yfinance stale ex-date problem now PROVEN (ADBE 2005, AMD 1995)
- Failure rate across full 500 tickers: UNKNOWN — measure in next scan
- NYSE holidays not blocked
- No dividend safety / payout ratio check
- No earnings-date avoidance
- No position sizing, exit rules, or execution

## Signal Frequency
RSI < 38 AND price > 200D MA AND ex-date within 21 days is **sparse**.
Zero signals is **normal and correct** in a healthy market.
**Do not loosen RSI threshold. The selectivity is the point.**

## Validated Run History
| Date | Command | Result | Notes |
|---|---|---|---|
| 2026-05-01 | `./run_bot.sh --dry-run --limit 10 --show-all` | PASS | No Telegram, no history |
| 2026-05-03 | `./run_bot.sh --limit 10 --show-all` | Weekend guard PASS | Exited cleanly |
| 2026-05-03 | `./run_bot.sh --limit 10 --show-all --force-weekend` | PASS | 0 signals, history.json empty |

## Commit History
| Hash | Description |
|---|---|
| eb5de68 | Initial dividend capture scanner |
| 04ff0ea | docs: update control files after first commit and v1.1 planning |
| (thesis) | docs: thesis reframe to Dividend Quality Pullback Scanner |

Verify actual state with `git log --oneline -5` at session start.

## v1.1 Roadmap (locked order)
1. ~~Telegram `.env` setup + delivery test~~ **DONE**
2. **Full 500-ticker scan + reason-count audit** ← next
   Categorise every skip into:
   - valid forward ex-date found
   - stale / past ex-date
   - ex-date outside 21-day window
   - no ex-date available
   - yfinance / API error
   - technical filter failed (RSI or MA)
   - signal generated
3. CSV export / report mode
4. Post-signal tracking skeleton (date, ticker, price at signal, SPY price at signal)
5. NYSE holiday guard (after audit confirms relevance)
6. Secondary ex-date source (after audit quantifies yfinance failure rate)

## Success Metrics (track from first live signals)
| Metric | Notes |
|---|---|
| % S&P 500 with usable forward ex-date | Measures yfinance coverage quality |
| Signals per month | Baseline signal frequency |
| Avg return at 1/3/5/10/20 trading days | Core performance measurement |
| Win rate post-signal | % profitable at each interval |
| Max drawdown post-signal | Downside risk per signal |
| Outperformance vs SPY | Primary benchmark |
| Signal quality by sector | Concentration and bias check |

## v1.2 Candidates
- Dividend quality filters (payout ratio, consecutive dividend years, debt/equity)
- Earnings-date avoidance window
- Valuation context (P/E vs sector median)
- Sector concentration control
- Ex-date revision detection / dedup TTL
- Scan optimisation (threading/async) — only after reliability proven
- Repo and file rename to match product direction
