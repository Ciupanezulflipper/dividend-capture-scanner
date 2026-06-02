"""
Post-signal performance audit for dividend-capture-scanner.

Reads all local scan reports, isolates signals, fetches historical
price data via yfinance, and produces performance metrics per signal.

Usage:
  python3 tools/audit_signal_performance.py [--signals-file path] [--good-threshold N] [--bad-threshold N]
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*auto_adjust.*")

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"
TODAY = date.today()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_date(val):
    if not val or str(val).strip() in ("", "nan", "None"):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _safe_float(val):
    try:
        v = str(val).strip()
        if v in ("", "nan", "None"):
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _git_short_hash():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _strip_tz(series):
    """Return a copy of the series with a tz-naive DatetimeIndex."""
    if series is None or series.empty:
        return series
    if getattr(series.index, "tz", None) is not None:
        series = series.copy()
        series.index = series.index.tz_localize(None)
    return series


def _trading_day_offset(price_series, base_date, n_days):
    """Return close price n trading days after base_date."""
    s = _strip_tz(price_series)
    trading_dates = s.index[s.index.normalize() > pd.Timestamp(base_date)]
    if len(trading_dates) < n_days:
        return None, None
    target_ts = trading_dates[n_days - 1]
    return float(s.loc[target_ts]), target_ts.date()


def _last_before(price_series, cutoff_date):
    """Return last close strictly before cutoff_date."""
    s = _strip_tz(price_series)
    mask = s.index.normalize() < pd.Timestamp(cutoff_date)
    subset = s[mask]
    if subset.empty:
        return None, None
    ts = subset.index[-1]
    return float(subset.iloc[-1]), ts.date()


def _first_on_or_after(price_series, cutoff_date):
    """Return first close on or after cutoff_date."""
    s = _strip_tz(price_series)
    mask = s.index.normalize() >= pd.Timestamp(cutoff_date)
    subset = s[mask]
    if subset.empty:
        return None, None
    ts = subset.index[0]
    return float(subset.iloc[0]), ts.date()


def _pct_return(alert_price, close_price):
    if alert_price and close_price and alert_price != 0:
        return round((close_price - alert_price) / alert_price * 100, 4)
    return None


def _median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return round(vals[mid], 4)
    return round((vals[mid - 1] + vals[mid]) / 2, 4)


# ---------------------------------------------------------------------------
# 1. load scanner reports
# ---------------------------------------------------------------------------

def load_scanner_signals():
    pattern = REPORTS_DIR.rglob("scan_report_*.csv")
    rows = []
    report_paths = sorted(pattern)
    report_count = len(report_paths)

    for csv_path in report_paths:
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sig = row.get("signal_passed", "").strip().lower()
                    rc = row.get("reason_category", "").strip()
                    if sig == "true" or rc == "signal_generated":
                        row["_source_report"] = str(csv_path.relative_to(REPO_ROOT))
                        rows.append(row)
        except Exception as exc:
            print(f"  WARNING: could not read {csv_path}: {exc}", file=sys.stderr)

    return rows, report_count


# ---------------------------------------------------------------------------
# 2. load optional manual seed CSV
# ---------------------------------------------------------------------------

def load_manual_signals(path):
    manual = []
    if not path or not Path(path).exists():
        return manual
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["_source_report"] = "manual"
            row["_is_manual"] = True
            manual.append(row)
    return manual


# ---------------------------------------------------------------------------
# 3. extract + deduplicate
# ---------------------------------------------------------------------------

def extract_signal(row):
    ex_date_raw = row.get("ex_date", "").strip()
    if not ex_date_raw:
        ex_date_raw = row.get("chosen_ex_date", "").strip()

    return {
        "scan_date":          row.get("scan_date", "").strip(),
        "symbol":             row.get("symbol", "").strip().upper(),
        "alert_price":        _safe_float(row.get("price") or row.get("alert_price")),
        "ex_date":            ex_date_raw,
        "days_to_ex_date":    _safe_float(row.get("days_to_ex_date")),
        "dividend_yield_pct": _safe_float(row.get("dividend_yield_pct")),
        "rsi14":              _safe_float(row.get("rsi14")),
        "ma200":              _safe_float(row.get("ma200")),
        "audit_flags":        row.get("audit_flags", "").strip(),
        "reason_category":    row.get("reason_category", "").strip(),
        "source_report":      row.get("_source_report", ""),
        "source_note":        row.get("source_note", "").strip(),
        "dividend_amount_manual": _safe_float(row.get("dividend_amount")),
        "_is_manual":         row.get("_is_manual", False),
    }


def deduplicate(signals):
    """Keep earliest scan_date per (symbol, ex_date)."""
    seen = {}
    for sig in signals:
        key = (sig["symbol"], sig["ex_date"])
        if key not in seen:
            seen[key] = sig
        else:
            existing_date = _parse_date(seen[key]["scan_date"])
            this_date = _parse_date(sig["scan_date"])
            if existing_date and this_date and this_date < existing_date:
                seen[key] = sig
    return list(seen.values())


# ---------------------------------------------------------------------------
# 4. grade group from audit_flags
# ---------------------------------------------------------------------------

def grade_group(flags):
    f = flags.lower() if flags else ""
    has_low_yield = "low_yield_candidate" in f
    has_ex_close  = "ex_date_too_close_candidate" in f
    has_other     = bool(f) and not (has_low_yield or has_ex_close) and f != "valid_forward_ex_date_in_window"

    if not has_low_yield and not has_ex_close and not has_other:
        return "CLEAN"
    if has_low_yield and not has_ex_close and not has_other:
        return "LOW_YIELD"
    if has_ex_close and not has_low_yield and not has_other:
        return "EX_DATE_CLOSE"
    return "MIXED_FLAGGED"


# ---------------------------------------------------------------------------
# 5. fetch market data
# ---------------------------------------------------------------------------

def fetch_market_data(signals):
    """
    Batch-fetch yfinance data for all symbols + SPY.
    Returns {symbol: pd.Series of Close prices}.
    Falls back per-symbol on batch failure.
    """
    if not signals:
        return {}, set(), set()

    # determine date range per symbol then find global min/max
    date_ranges = {}
    for sig in signals:
        sd = _parse_date(sig["scan_date"])
        ex = _parse_date(sig["ex_date"])
        if sd is None:
            continue
        start = sd - timedelta(days=3)
        if ex:
            end = ex + timedelta(days=15)
        else:
            end = sd + timedelta(days=35)
        sym = sig["symbol"]
        if sym not in date_ranges:
            date_ranges[sym] = (start, end)
        else:
            existing_start, existing_end = date_ranges[sym]
            date_ranges[sym] = (min(existing_start, start), max(existing_end, end))

    global_start = min(v[0] for v in date_ranges.values())
    global_end   = max(v[1] for v in date_ranges.values())

    symbols = sorted(date_ranges.keys())
    all_syms = symbols + ["SPY"]

    price_data = {}
    successful = set()
    failed = set()

    # batch attempt
    try:
        raw = yf.download(
            all_syms,
            start=str(global_start),
            end=str(global_end + timedelta(days=1)),
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        close = raw["Close"] if "Close" in raw.columns else raw.xs("Close", axis=1, level=0)
        for sym in all_syms:
            if sym in close.columns:
                s = close[sym].dropna()
                if not s.empty:
                    price_data[sym] = s
                    successful.add(sym)
                else:
                    failed.add(sym)
    except Exception as exc:
        print(f"  WARNING: batch yfinance download failed ({exc}), falling back per-symbol",
              file=sys.stderr)

    # per-symbol fallback for anything not in batch result
    for sym in all_syms:
        if sym in price_data:
            continue
        sym_start = date_ranges.get(sym, (global_start, global_end))[0]
        sym_end   = date_ranges.get(sym, (global_start, global_end))[1]
        try:
            raw = yf.download(
                sym,
                start=str(sym_start),
                end=str(sym_end + timedelta(days=1)),
                auto_adjust=False,
                progress=False,
            )
            if raw.empty:
                failed.add(sym)
                continue
            close_col = raw["Close"] if "Close" in raw.columns else None
            if close_col is None:
                failed.add(sym)
                continue
            s = close_col.squeeze().dropna()
            if s.empty:
                failed.add(sym)
            else:
                price_data[sym] = s
                successful.add(sym)
        except Exception as exc:
            print(f"  WARNING: yfinance failed for {sym}: {exc}", file=sys.stderr)
            failed.add(sym)

    return price_data, successful, failed


# ---------------------------------------------------------------------------
# 6. fetch dividend data from yfinance
# ---------------------------------------------------------------------------

def fetch_dividends(symbols):
    """Return {symbol: pd.Series of dividends indexed by date}."""
    divs = {}
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            d = ticker.dividends
            if d is not None and not d.empty:
                divs[sym] = d
        except Exception:
            pass
    return divs


def find_dividend_near_exdate(div_series, ex_date, window_days=5):
    """
    Look for a dividend record within window_days of ex_date.
    yfinance sometimes records dividends on ex_date or nearby.
    Returns (amount, date_str) or (None, None).
    """
    if div_series is None or div_series.empty or ex_date is None:
        return None, None
    div_series = _strip_tz(div_series)
    ex = pd.Timestamp(ex_date)
    lower = ex - timedelta(days=window_days)
    upper = ex + timedelta(days=window_days)
    mask = (div_series.index.normalize() >= lower) & (div_series.index.normalize() <= upper)
    subset = div_series[mask]
    if subset.empty:
        return None, None
    idx = (subset.index.normalize() - ex).map(abs).argmin()
    return float(subset.iloc[idx]), str(subset.index[idx].date())


# ---------------------------------------------------------------------------
# 7. classify signal outcome
# ---------------------------------------------------------------------------

def classify(price_return_5d, pre_ex_return, good_threshold, bad_threshold, scan_date, ex_date):
    """GOOD / BAD / NEUTRAL / PENDING."""
    scan_d = _parse_date(scan_date)
    ex_d   = _parse_date(ex_date)
    ref_date = ex_d if ex_d else (scan_d + timedelta(days=30) if scan_d else None)

    if ref_date and TODAY < ref_date + timedelta(days=7):
        trading_days_needed = 5
        if scan_d:
            elapsed = (TODAY - scan_d).days
            if elapsed < trading_days_needed + 2:
                return "PENDING"

    best = None
    for r in [price_return_5d, pre_ex_return]:
        if r is not None:
            best = r if best is None else max(best, r)
    worst = None
    for r in [price_return_5d, pre_ex_return]:
        if r is not None:
            worst = r if worst is None else min(worst, r)

    if best is None:
        return "PENDING"
    if best >= good_threshold:
        return "GOOD"
    if worst is not None and worst <= bad_threshold:
        return "BAD"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# 8. build per-signal result row
# ---------------------------------------------------------------------------

def build_result(sig, price_data, div_data, good_thr, bad_thr):
    sym = sig["symbol"]
    scan_d = _parse_date(sig["scan_date"])
    ex_d   = _parse_date(sig["ex_date"])
    alert_price = sig["alert_price"]

    series = price_data.get(sym)
    spy_series = price_data.get("SPY")

    def _r(close_price):
        return _pct_return(alert_price, close_price)

    # price checkpoints
    p1d_close, p1d_date   = _trading_day_offset(series, scan_d, 1)  if series is not None and scan_d else (None, None)
    p3d_close, p3d_date   = _trading_day_offset(series, scan_d, 3)  if series is not None and scan_d else (None, None)
    p5d_close, p5d_date   = _trading_day_offset(series, scan_d, 5)  if series is not None and scan_d else (None, None)
    p10d_close, p10d_date = _trading_day_offset(series, scan_d, 10) if series is not None and scan_d else (None, None)
    pre_ex_close, pre_ex_date   = _last_before(series, ex_d)         if series is not None and ex_d else (None, None)
    post_ex_close, post_ex_date = _first_on_or_after(series, ex_d)   if series is not None and ex_d else (None, None)

    pr_1d  = _r(p1d_close)
    pr_3d  = _r(p3d_close)
    pr_5d  = _r(p5d_close)
    pr_10d = _r(p10d_close)
    pre_ex_pr  = _r(pre_ex_close)
    post_ex_pr = _r(post_ex_close)

    # SPY matching returns
    def _spy_r(ref_date_obj, n_days=None):
        if spy_series is None or ref_date_obj is None:
            return None
        spy_alert, _ = _first_on_or_after(spy_series, scan_d) if scan_d else (None, None)
        if n_days:
            spy_close, _ = _trading_day_offset(spy_series, scan_d, n_days)
        else:
            spy_close, _ = _last_before(spy_series, ref_date_obj) if ref_date_obj else (None, None)
        return _pct_return(spy_alert, spy_close)

    spy_1d  = _spy_r(p1d_date,  n_days=1)
    spy_3d  = _spy_r(p3d_date,  n_days=3)
    spy_5d  = _spy_r(p5d_date,  n_days=5)
    spy_10d = _spy_r(p10d_date, n_days=10)
    spy_pre_ex = _spy_r(pre_ex_date)

    # dividend amount resolution
    div_amount = None
    div_source = "none"
    div_date_found = None

    # yfinance dividends
    sym_divs = div_data.get(sym)
    yf_div, yf_div_date = find_dividend_near_exdate(sym_divs, ex_d)
    if yf_div is not None:
        div_amount = yf_div
        div_source = "yfinance"
        div_date_found = yf_div_date

    # manual fallback
    if div_amount is None and sig.get("dividend_amount_manual") is not None:
        div_amount = sig["dividend_amount_manual"]
        div_source = "manual"

    dividend_return_pct = None
    if div_amount is not None and alert_price:
        dividend_return_pct = round(div_amount / alert_price * 100, 4)

    # rough estimate (clearly labeled, not used in total_return)
    rough_estimated_div = None
    dy = sig["dividend_yield_pct"]
    if dy and alert_price:
        rough_estimated_div = round(dy / 4 / 100 * alert_price, 4)

    # actual_total_return_pct per checkpoint
    def _total_return(price_ret, include_div, checkpoint_date):
        if price_ret is None:
            return None
        if not include_div or div_amount is None or dividend_return_pct is None:
            return price_ret if not include_div else None
        return round(price_ret + dividend_return_pct, 4)

    # include dividend only on/after ex_date
    def _include_div(chk_date):
        if chk_date is None or ex_d is None:
            return False
        return chk_date >= ex_d

    atr_pre_ex  = _pct_return(alert_price, pre_ex_close)
    atr_post_ex = None
    if post_ex_close is not None and div_amount is not None:
        atr_post_ex = round((post_ex_close - alert_price) / alert_price * 100 + dividend_return_pct, 4) if alert_price else None
    elif post_ex_close is not None:
        atr_post_ex = _r(post_ex_close)

    # 5d actual total return: add dividend only if 5d checkpoint lands on/after ex_date
    atr_5d = None
    if pr_5d is not None:
        if p5d_date and ex_d and p5d_date >= ex_d:
            if dividend_return_pct is not None:
                atr_5d = round(pr_5d + dividend_return_pct, 4)
            # else: post-ex checkpoint but no div known — leave null
        else:
            atr_5d = pr_5d  # pre-ex checkpoint: total return == price return

    classification = classify(pr_5d, pre_ex_pr, good_thr, bad_thr, sig["scan_date"], sig["ex_date"])
    grade = grade_group(sig["audit_flags"])

    return {
        "scan_date":                  sig["scan_date"],
        "symbol":                     sym,
        "alert_price":                alert_price,
        "ex_date":                    sig["ex_date"],
        "days_to_ex_date":            sig["days_to_ex_date"],
        "dividend_yield_pct":         sig["dividend_yield_pct"],
        "rsi14":                      sig["rsi14"],
        "ma200":                      sig["ma200"],
        "audit_flags":                sig["audit_flags"],
        "reason_category":            sig["reason_category"],
        "grade_group":                grade,
        "source_report":              sig["source_report"],
        "source_note":                sig["source_note"],
        # price checkpoints
        "close_1d":                   p1d_close,
        "close_3d":                   p3d_close,
        "close_5d":                   p5d_close,
        "close_10d":                  p10d_close,
        "pre_ex_close":               pre_ex_close,
        "post_ex_close":              post_ex_close,
        "pre_ex_date":                str(pre_ex_date) if pre_ex_date else None,
        "post_ex_date":               str(post_ex_date) if post_ex_date else None,
        # price returns
        "price_return_pct_1d":        pr_1d,
        "price_return_pct_3d":        pr_3d,
        "price_return_pct_5d":        pr_5d,
        "price_return_pct_10d":       pr_10d,
        "pre_ex_price_return_pct":    pre_ex_pr,
        "post_ex_price_return_pct":   post_ex_pr,
        # SPY benchmark
        "spy_return_pct_1d":          spy_1d,
        "spy_return_pct_3d":          spy_3d,
        "spy_return_pct_5d":          spy_5d,
        "spy_return_pct_10d":         spy_10d,
        "spy_pre_ex_return_pct":      spy_pre_ex,
        # dividend
        "dividend_amount_used":       div_amount,
        "dividend_amount_source":     div_source,
        "dividend_date_found":        div_date_found,
        "dividend_return_pct":        dividend_return_pct,
        "rough_estimated_dividend_amount_ESTIMATE_ONLY": rough_estimated_div,
        # total return
        "actual_total_return_pct_5d": atr_5d,
        "pre_ex_total_return_pct":    atr_pre_ex,
        "post_ex_total_return_pct":   atr_post_ex,
        # classification
        "classification":             classification,
    }


# ---------------------------------------------------------------------------
# 9. summaries
# ---------------------------------------------------------------------------

def _resolved_rates(good, neutral, bad):
    resolved = good + neutral + bad
    if resolved == 0:
        return resolved, None, None, None
    return (
        resolved,
        round(good    / resolved * 100, 2),
        round(neutral / resolved * 100, 2),
        round(bad     / resolved * 100, 2),
    )


def summary_by_grade(results):
    groups = {}
    for r in results:
        g = r["grade_group"]
        if g not in groups:
            groups[g] = {
                "grade_group": g,
                "good_count": 0, "neutral_count": 0, "bad_count": 0, "pending_count": 0,
                "_5d": [], "_pre_ex": [], "_atr_5d": [], "_pre_ex_atr": [],
            }
        cl = r["classification"]
        groups[g][f"{cl.lower()}_count"] += 1
        if r["price_return_pct_5d"] is not None:
            groups[g]["_5d"].append(r["price_return_pct_5d"])
        if r["pre_ex_price_return_pct"] is not None:
            groups[g]["_pre_ex"].append(r["pre_ex_price_return_pct"])
        if r.get("actual_total_return_pct_5d") is not None:
            groups[g]["_atr_5d"].append(r["actual_total_return_pct_5d"])
        if r["pre_ex_total_return_pct"] is not None:
            groups[g]["_pre_ex_atr"].append(r["pre_ex_total_return_pct"])

    rows = []
    for g, d in sorted(groups.items()):
        good, neutral, bad, pending = (
            d["good_count"], d["neutral_count"], d["bad_count"], d["pending_count"]
        )
        resolved, good_rate, neutral_rate, bad_rate = _resolved_rates(good, neutral, bad)
        v5, vp = d["_5d"], d["_pre_ex"]
        rows.append({
            "grade_group":                    g,
            "total_signals":                  good + neutral + bad + pending,
            "resolved_signals":               resolved,
            "pending_signals":                pending,
            "good_count":                     good,
            "neutral_count":                  neutral,
            "bad_count":                      bad,
            "pending_count":                  pending,
            "good_rate_resolved_pct":         good_rate,
            "neutral_rate_resolved_pct":      neutral_rate,
            "bad_rate_resolved_pct":          bad_rate,
            "mean_price_return_pct_5d":       round(sum(v5) / len(v5), 4) if v5 else None,
            "median_price_return_pct_5d":     _median(v5),
            "mean_pre_ex_price_return_pct":   round(sum(vp) / len(vp), 4) if vp else None,
            "median_pre_ex_price_return_pct": _median(vp),
            "median_actual_total_return_pct_5d":       _median(d["_atr_5d"]),
            "median_pre_ex_actual_total_return_pct":   _median(d["_pre_ex_atr"]),
        })
    return rows


def summary_by_symbol(results):
    syms = {}
    for r in results:
        s = r["symbol"]
        if s not in syms:
            syms[s] = {
                "symbol": s,
                "good_count": 0, "neutral_count": 0, "bad_count": 0, "pending_count": 0,
                "_5d": [], "_pre_ex": [], "_atr_5d": [], "_pre_ex_atr": [],
            }
        cl = r["classification"]
        syms[s][f"{cl.lower()}_count"] += 1
        if r["price_return_pct_5d"] is not None:
            syms[s]["_5d"].append(r["price_return_pct_5d"])
        if r["pre_ex_price_return_pct"] is not None:
            syms[s]["_pre_ex"].append(r["pre_ex_price_return_pct"])
        if r.get("actual_total_return_pct_5d") is not None:
            syms[s]["_atr_5d"].append(r["actual_total_return_pct_5d"])
        if r["pre_ex_total_return_pct"] is not None:
            syms[s]["_pre_ex_atr"].append(r["pre_ex_total_return_pct"])

    rows = []
    for s, d in sorted(syms.items()):
        good, neutral, bad, pending = (
            d["good_count"], d["neutral_count"], d["bad_count"], d["pending_count"]
        )
        resolved, good_rate, neutral_rate, bad_rate = _resolved_rates(good, neutral, bad)
        v5, vp = d["_5d"], d["_pre_ex"]
        rows.append({
            "symbol":                         s,
            "total_signals":                  good + neutral + bad + pending,
            "resolved_signals":               resolved,
            "pending_signals":                pending,
            "good_count":                     good,
            "neutral_count":                  neutral,
            "bad_count":                      bad,
            "pending_count":                  pending,
            "good_rate_resolved_pct":         good_rate,
            "neutral_rate_resolved_pct":      neutral_rate,
            "bad_rate_resolved_pct":          bad_rate,
            "mean_price_return_pct_5d":       round(sum(v5) / len(v5), 4) if v5 else None,
            "median_price_return_pct_5d":     _median(v5),
            "mean_pre_ex_price_return_pct":   round(sum(vp) / len(vp), 4) if vp else None,
            "median_pre_ex_price_return_pct": _median(vp),
            "median_actual_total_return_pct_5d":       _median(d["_atr_5d"]),
            "median_pre_ex_actual_total_return_pct":   _median(d["_pre_ex_atr"]),
        })
    return rows


# ---------------------------------------------------------------------------
# 10. write outputs
# ---------------------------------------------------------------------------

def write_outputs(results, grade_rows, symbol_rows, meta):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = REPORTS_DIR / f"performance_audit_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # signal_performance.csv
    if results:
        keys = list(results[0].keys())
        with open(out_dir / "signal_performance.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(results)

    # summary_by_grade.csv
    if grade_rows:
        with open(out_dir / "summary_by_grade.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(grade_rows[0].keys()))
            w.writeheader()
            w.writerows(grade_rows)

    # summary_by_symbol.csv
    if symbol_rows:
        with open(out_dir / "summary_by_symbol.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(symbol_rows[0].keys()))
            w.writeheader()
            w.writerows(symbol_rows)

    # audit_metadata.json
    with open(out_dir / "audit_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    return out_dir


# ---------------------------------------------------------------------------
# 11. console summary
# ---------------------------------------------------------------------------

def _fmt(val, suffix="%", width=7):
    if val is None:
        return "n/a".rjust(width)
    return f"{val:+.2f}{suffix}".rjust(width + len(suffix))


def print_console_summary(results, failed_syms, meta):
    sc = meta.get("signal_counts", {})
    total    = sc.get("total_signals", len(results))
    resolved = sc.get("resolved_signals", 0)
    pending  = sc.get("pending_signals", 0)
    good     = sc.get("good_count", 0)
    neutral  = sc.get("neutral_count", 0)
    bad      = sc.get("bad_count", 0)
    good_rate    = sc.get("good_rate_resolved_pct")
    neutral_rate = sc.get("neutral_rate_resolved_pct")
    bad_rate     = sc.get("bad_rate_resolved_pct")

    # collect returns for CLEAN vs FLAGGED (use 5d, fall back to pre_ex)
    clean_5d, clean_pre, flagged_5d, flagged_pre = [], [], [], []
    clean_resolved, clean_pending = 0, 0
    flagged_resolved, flagged_pending = 0, 0

    all_ret = []
    for r in results:
        ret5  = r["price_return_pct_5d"]
        retpx = r["pre_ex_price_return_pct"]
        best  = ret5 if ret5 is not None else retpx
        sym   = r["symbol"]
        is_clean = r["grade_group"] == "CLEAN"
        is_pending = r["classification"] == "PENDING"

        if best is not None:
            all_ret.append((sym, best))

        if is_clean:
            if ret5  is not None: clean_5d.append(ret5)
            if retpx is not None: clean_pre.append(retpx)
            if is_pending: clean_pending += 1
            else:          clean_resolved += 1
        else:
            if ret5  is not None: flagged_5d.append(ret5)
            if retpx is not None: flagged_pre.append(retpx)
            if is_pending: flagged_pending += 1
            else:          flagged_resolved += 1

    top5 = sorted(all_ret, key=lambda x: -x[1])[:5]
    bot5 = sorted(all_ret, key=lambda x:  x[1])[:5]
    div_sources = meta.get("dividend_amount_sources", {})

    print("\n" + "=" * 60)
    print("  POST-SIGNAL PERFORMANCE AUDIT")
    print("=" * 60)
    print(f"  Reports scanned:       {meta['input_report_count']}")
    print(f"  Signals before dedup:  {meta['signal_rows_before_dedup']}")
    print(f"  Signals after dedup:   {meta['signal_count_after_dedup']}")
    print(f"  Manual signals:        {meta['manual_signal_count']}")
    print(f"  Thresholds:            GOOD >= {meta['classification_thresholds']['good']}%  |  BAD <= {meta['classification_thresholds']['bad']}%")
    print()
    print(f"  Total signals:         {total}")
    print(f"  Resolved signals:      {resolved}  (GOOD + NEUTRAL + BAD)")
    print(f"  Pending signals:       {pending}")
    print()
    print(f"  GOOD:    {good:3d}" + (f"  ({good_rate:.1f}% of resolved)" if good_rate is not None else ""))
    print(f"  NEUTRAL: {neutral:3d}" + (f"  ({neutral_rate:.1f}% of resolved)" if neutral_rate is not None else ""))
    print(f"  BAD:     {bad:3d}" + (f"  ({bad_rate:.1f}% of resolved)" if bad_rate is not None else ""))
    print(f"  PENDING: {pending:3d}")
    print()

    def _group_line(label, vals_5d, vals_pre, n_resolved, n_pending):
        mean5   = round(sum(vals_5d)  / len(vals_5d),  2) if vals_5d  else None
        med5    = _median(vals_5d)
        mean_px = round(sum(vals_pre) / len(vals_pre), 2) if vals_pre else None
        med_px  = _median(vals_pre)
        print(f"  {label} signals  (resolved={n_resolved}, pending={n_pending}):")
        print(f"    5d price:  mean={_fmt(mean5)}  median={_fmt(med5)}")
        print(f"    pre-ex:    mean={_fmt(mean_px)}  median={_fmt(med_px)}")

    _group_line("CLEAN",   clean_5d,   clean_pre,   clean_resolved,   clean_pending)
    print()
    _group_line("FLAGGED", flagged_5d, flagged_pre, flagged_resolved, flagged_pending)
    print()

    if top5:
        print("  Top 5 winners (5d or pre-ex return):")
        for sym, ret in top5:
            print(f"    {sym:8s}  {ret:+.2f}%")
    print()
    if bot5:
        print("  Top 5 losers (5d or pre-ex return):")
        for sym, ret in bot5:
            print(f"    {sym:8s}  {ret:+.2f}%")
    print()

    if failed_syms:
        print(f"  Failed data fetches ({len(failed_syms)}): {', '.join(sorted(failed_syms))}")
    else:
        print("  Failed data fetches: none")
    print()

    print("  Dividend amount sources:")
    for src, cnt in div_sources.items():
        print(f"    {src}: {cnt}")
    print()

    if meta.get("warnings"):
        print("  Warnings:")
        for w in meta["warnings"]:
            print(f"    - {w}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Post-signal performance audit")
    parser.add_argument("--signals-file", default=None,
                        help="Optional manual signal seed CSV (data/manual_signal_audit_seed.csv)")
    parser.add_argument("--good-threshold", type=float, default=2.0,
                        help="Min return %% to classify GOOD (default 2.0)")
    parser.add_argument("--bad-threshold", type=float, default=-2.0,
                        help="Max return %% to classify BAD (default -2.0)")
    args = parser.parse_args()

    print("Loading scanner reports...")
    scanner_rows, report_count = load_scanner_signals()
    print(f"  Found {len(scanner_rows)} signal rows across {report_count} reports")

    manual_rows = []
    if args.signals_file:
        manual_rows = load_manual_signals(args.signals_file)
        print(f"  Loaded {len(manual_rows)} manual signals from {args.signals_file}")

    all_raw = [extract_signal(r) for r in scanner_rows + manual_rows]
    pre_dedup = len(all_raw)

    deduped = deduplicate(all_raw)
    print(f"  After dedup: {len(deduped)} unique (symbol, ex_date) signals")

    if not deduped:
        print("No signals to audit. Exiting.")
        return

    print("Fetching market data (yfinance)...")
    price_data, successful_syms, failed_syms = fetch_market_data(deduped)
    print(f"  Successful: {len(successful_syms)}  Failed: {len(failed_syms)}")

    print("Fetching dividend data (yfinance)...")
    all_symbols = list({s["symbol"] for s in deduped})
    div_data = fetch_dividends(all_symbols)
    print(f"  Dividend series fetched for {len(div_data)} symbols")

    print("Computing signal performance...")
    results = []
    for sig in deduped:
        try:
            row = build_result(sig, price_data, div_data, args.good_threshold, args.bad_threshold)
            results.append(row)
        except Exception as exc:
            print(f"  WARNING: failed to process {sig['symbol']}: {exc}", file=sys.stderr)

    grade_rows = summary_by_grade(results)
    symbol_rows = summary_by_symbol(results)

    div_source_counts = {"yfinance": 0, "manual": 0, "none": 0}
    for r in results:
        src = r.get("dividend_amount_source", "none")
        div_source_counts[src] = div_source_counts.get(src, 0) + 1

    counts = {"GOOD": 0, "NEUTRAL": 0, "BAD": 0, "PENDING": 0}
    for r in results:
        counts[r["classification"]] += 1
    resolved = counts["GOOD"] + counts["NEUTRAL"] + counts["BAD"]
    pending  = counts["PENDING"]
    resolved_r, good_rate, neutral_rate, bad_rate = _resolved_rates(
        counts["GOOD"], counts["NEUTRAL"], counts["BAD"]
    )

    all_5d     = [r["price_return_pct_5d"]      for r in results if r["price_return_pct_5d"]      is not None]
    all_pre_ex = [r["pre_ex_price_return_pct"]   for r in results if r["pre_ex_price_return_pct"]  is not None]
    all_atr_5d = [r.get("actual_total_return_pct_5d") for r in results
                  if r.get("actual_total_return_pct_5d") is not None]
    all_pre_atr = [r["pre_ex_total_return_pct"]  for r in results if r["pre_ex_total_return_pct"]  is not None]

    meta = {
        "generated_at":            datetime.now().isoformat(),
        "repo_commit_short_hash":  _git_short_hash(),
        "input_report_count":      report_count,
        "signal_rows_before_dedup": pre_dedup,
        "signal_count_after_dedup": len(deduped),
        "manual_signal_count":     len(manual_rows),
        "signal_counts": {
            "total_signals":           len(results),
            "resolved_signals":        resolved,
            "pending_signals":         pending,
            "good_count":              counts["GOOD"],
            "neutral_count":           counts["NEUTRAL"],
            "bad_count":               counts["BAD"],
            "pending_count":           pending,
            "good_rate_resolved_pct":    good_rate,
            "neutral_rate_resolved_pct": neutral_rate,
            "bad_rate_resolved_pct":     bad_rate,
        },
        "overall_returns": {
            "mean_price_return_pct_5d":       round(sum(all_5d) / len(all_5d), 4) if all_5d else None,
            "median_price_return_pct_5d":     _median(all_5d),
            "mean_pre_ex_price_return_pct":   round(sum(all_pre_ex) / len(all_pre_ex), 4) if all_pre_ex else None,
            "median_pre_ex_price_return_pct": _median(all_pre_ex),
            "median_actual_total_return_pct_5d":     _median(all_atr_5d),
            "median_pre_ex_actual_total_return_pct": _median(all_pre_atr),
        },
        "successful_yfinance_symbols": sorted(successful_syms),
        "failed_yfinance_symbols":     sorted(failed_syms),
        "classification_thresholds": {
            "good": args.good_threshold,
            "bad":  args.bad_threshold,
        },
        "dividend_amount_sources": div_source_counts,
        "warnings": (
            [f"yfinance data unavailable for: {', '.join(sorted(failed_syms))}"]
            if failed_syms else []
        ),
    }

    out_dir = write_outputs(results, grade_rows, symbol_rows, meta)
    print(f"\nOutputs written to: {out_dir.relative_to(REPO_ROOT)}")

    print_console_summary(results, failed_syms, meta)


if __name__ == "__main__":
    main()
