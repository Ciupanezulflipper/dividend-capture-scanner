#!/usr/bin/env python3
"""
Dividend Quality Pullback Scanner — v1.1 audit/report layer

Scans S&P 500 for stocks whose ex-dividend date falls within the next
WINDOW_DAYS calendar days and that satisfy entry signal criteria:

  RSI(14) < RSI_THRESHOLD  AND  price > MA(MA_LENGTH)

Sends Telegram alerts and logs results. Dry-run mode skips Telegram and
history writes.

v1.1 adds audit visibility before hard filters are activated:
- dividend yield visibility
- days-to-ex-date visibility
- structured reason categories
- CSV report output
- audit-only candidate flags for low yield and ex-date too close

This script does not execute trades.
"""

import argparse
import csv
import hashlib
import json
import logging
import math
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from io import StringIO
from typing import Any, Optional

import pandas as pd
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import box

# ── Optional pandas-ta (RSI fallback to pure-pandas if unavailable) ──────────
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

# ── Project root and env ─────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")

# ── Constants / env defaults ──────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
HISTORY_FILE = PROJECT_ROOT / os.getenv("HISTORY_FILE", "history.json")
LOG_FILE = PROJECT_ROOT / os.getenv("LOG_FILE", "stock_scan.log")

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

console = Console()

REPORT_FIELDS = [
    "scan_date",
    "symbol",
    "ex_date",
    "days_to_ex_date",
    "yf_ex_date",
    "yf_ex_date_source",
    "yf_ex_date_error",
    "chosen_ex_date",
    "chosen_ex_date_source",
    "ex_date_match_status",
    "ex_date_audit_flags",
    "price",
    "ma200",
    "rsi14",
    "dividend_yield_pct",
    "signal_passed",
    "reason_category",
    "audit_flags",
    "passes_audit_min_yield",
    "passes_audit_min_days_to_ex_date",
    "error",
]


# ── Logging setup ─────────────────────────────────────────────────────────────

def setup_logging(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("dividend_scanner")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


# ── S&P 500 ticker fetch ──────────────────────────────────────────────────────

def fetch_sp500_tickers(logger: logging.Logger) -> list[str]:
    """Return list of S&P 500 tickers from Wikipedia."""
    try:
        response = requests.get(
            SP500_WIKI_URL,
            headers={"User-Agent": "Mozilla/5.0 DividendQualityPullbackScanner/1.1"},
            timeout=30,
        )
        response.raise_for_status()
        tables = pd.read_html(
            StringIO(response.text),
            attrs={"id": "constituents"},
            flavor="html5lib",
        )
        df = tables[0]
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        tickers = df[col].str.replace(".", "-", regex=False).tolist()
        logger.info("Fetched %d S&P 500 tickers from Wikipedia.", len(tickers))
        return tickers
    except Exception as exc:
        logger.error("Failed to fetch S&P 500 tickers: %s", exc)
        console.print(f"[red]ERROR fetching S&P 500 list: {exc}[/red]")
        sys.exit(1)


# ── Numeric and date helpers ──────────────────────────────────────────────────

def safe_float(value: Any) -> Optional[float]:
    """Convert yfinance/pandas values to a finite float when possible."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def parse_date_value(value: Any) -> Optional[date]:
    """Convert common yfinance date shapes into a date."""
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.to_pydatetime().date()

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, (list, tuple, set)):
        for item in value:
            parsed = parse_date_value(item)
            if parsed:
                return parsed
        return None

    num = safe_float(value)
    if num is not None and num > 0:
        try:
            ts = num / 1000 if num > 10_000_000_000 else num
            return datetime.fromtimestamp(ts, tz=timezone.utc).date()
        except Exception:
            return None

    try:
        parsed = pd.to_datetime(value, errors="coerce", utc=True)
        return None if pd.isna(parsed) else parsed.date()
    except Exception:
        return None


def fmt_float(value: Optional[float], digits: int = 2) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def normalize_report_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


# ── Ex-dividend and dividend yield discovery ─────────────────────────────────

def get_ticker_info(ticker_obj, logger: logging.Logger) -> dict[str, Any]:
    """Best-effort yfinance .info call. Returns empty dict on failure."""
    symbol = getattr(ticker_obj, "ticker", "UNKNOWN")
    try:
        info = ticker_obj.info
        return info if isinstance(info, dict) else {}
    except Exception as exc:
        logger.debug("%s info error: %s", symbol, exc)
        return {}


def _empty_ex_date_details() -> dict[str, Any]:
    return {
        "yf_ex_date": None,
        "yf_ex_date_source": "none",
        "yf_ex_date_error": "",
        "chosen_ex_date": None,
        "chosen_ex_date_source": "none",
        "ex_date_match_status": "both_missing",
        "ex_date_audit_flags": "no_usable_ex_date",
    }


def _found_yfinance_ex_date(parsed: date, source: str) -> dict[str, Any]:
    return {
        "yf_ex_date": parsed,
        "yf_ex_date_source": source,
        "yf_ex_date_error": "",
        "chosen_ex_date": parsed,
        "chosen_ex_date_source": source,
        "ex_date_match_status": "yf_only",
        "ex_date_audit_flags": "yfinance_ex_date_available",
    }


def get_ex_dividend_date_details(
    ticker_obj,
    logger: logging.Logger,
    info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Return yfinance ex-dividend date metadata.

    Phase 1 is audit-only:
    - No secondary provider is called.
    - Signal behaviour remains unchanged.
    - chosen_ex_date is still the yfinance date when available.
    """
    symbol = ticker_obj.ticker
    details = _empty_ex_date_details()

    try:
        cal = ticker_obj.calendar
        if cal is not None:
            if isinstance(cal, dict):
                for key in ("Ex-Dividend Date", "exDividendDate", "ex_dividend_date"):
                    parsed = parse_date_value(cal.get(key))
                    if parsed:
                        return _found_yfinance_ex_date(
                            parsed,
                            f"yfinance_calendar_dict:{key}",
                        )
            elif isinstance(cal, pd.DataFrame):
                if "Ex-Dividend Date" in cal.index:
                    parsed = parse_date_value(cal.loc["Ex-Dividend Date"].iloc[0])
                    if parsed:
                        return _found_yfinance_ex_date(
                            parsed,
                            "yfinance_calendar_dataframe:Ex-Dividend Date",
                        )
            elif isinstance(cal, pd.Series):
                for key in ("Ex-Dividend Date", "exDividendDate", "ex_dividend_date"):
                    if key in cal:
                        parsed = parse_date_value(cal[key])
                        if parsed:
                            return _found_yfinance_ex_date(
                                parsed,
                                f"yfinance_calendar_series:{key}",
                            )
    except Exception as exc:
        details["yf_ex_date_error"] = str(exc)[:200]
        details["ex_date_audit_flags"] = "yfinance_calendar_error|no_usable_ex_date"
        logger.debug("%s calendar error: %s", symbol, exc)

    info = info or get_ticker_info(ticker_obj, logger)
    for field in ("exDividendDate", "ex_dividend_date"):
        parsed = parse_date_value(info.get(field))
        if parsed:
            return _found_yfinance_ex_date(
                parsed,
                f"yfinance_info:{field}",
            )

    return details


def get_ex_dividend_date(
    ticker_obj,
    logger: logging.Logger,
    info: Optional[dict[str, Any]] = None,
) -> Optional[date]:
    """Backward-compatible wrapper returning only the chosen ex-dividend date."""
    details = get_ex_dividend_date_details(ticker_obj, logger, info=info)
    return details.get("chosen_ex_date")


MAX_REASONABLE_DIVIDEND_YIELD_PCT = 15.0


def sanitize_dividend_yield_pct(value: Optional[float]) -> Optional[float]:
    """
    Keep only plausible annualized dividend-yield percentages.

    This is data hygiene, not a strategy filter. Values above the cap are treated
    as invalid source data instead of being used for signal decisions.
    """
    if value is None:
        return None
    if value < 0:
        return None
    if value > MAX_REASONABLE_DIVIDEND_YIELD_PCT:
        return None
    return value


def get_dividend_yield_pct(info: dict[str, Any], price: Optional[float]) -> Optional[float]:
    """
    Return annualized dividend yield as percentage, for example 2.5 for 2.5%.

    yfinance yield units vary by field:
    - dividendYield currently appears as an already-percent value for stocks
      such as AAPL=0.38 meaning 0.38%, not 38%.
    - trailingAnnualDividendYield appears as a decimal fraction, e.g. 0.0036.
    - dividendRate / price has explicit units, so it is preferred when available.
    """
    annual_dividend = (
        safe_float(info.get("dividendRate"))
        or safe_float(info.get("forwardAnnualDividendRate"))
        or safe_float(info.get("trailingAnnualDividendRate"))
    )
    if annual_dividend is not None and price is not None and price > 0:
        derived_pct = (annual_dividend / price) * 100
        sanitized = sanitize_dividend_yield_pct(derived_pct)
        if sanitized is not None:
            return sanitized

    dividend_yield = safe_float(info.get("dividendYield"))
    if dividend_yield is not None:
        sanitized = sanitize_dividend_yield_pct(dividend_yield)
        if sanitized is not None:
            return sanitized

    forward_yield = safe_float(info.get("forwardDividendYield"))
    if forward_yield is not None:
        sanitized = sanitize_dividend_yield_pct(forward_yield)
        if sanitized is not None:
            return sanitized

    trailing_yield = safe_float(info.get("trailingAnnualDividendYield"))
    if trailing_yield is not None:
        trailing_pct = trailing_yield * 100 if trailing_yield <= 1 else trailing_yield
        sanitized = sanitize_dividend_yield_pct(trailing_pct)
        if sanitized is not None:
            return sanitized

    generic_yield = safe_float(info.get("yield"))
    if generic_yield is not None:
        generic_pct = generic_yield * 100 if generic_yield <= 1 else generic_yield
        sanitized = sanitize_dividend_yield_pct(generic_pct)
        if sanitized is not None:
            return sanitized

    return None


# ── RSI calculation ───────────────────────────────────────────────────────────

def _rsi_pandas(close: pd.Series, period: int = 14) -> pd.Series:
    """Pure-pandas Wilder RSI — used when pandas-ta is unavailable."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def compute_rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """Return latest RSI value or None if not enough data."""
    if len(close) < period + 1:
        return None
    try:
        if HAS_PANDAS_TA:
            rsi_series = ta.rsi(close, length=period)
        else:
            rsi_series = _rsi_pandas(close, period)
        val = rsi_series.dropna()
        return float(val.iloc[-1]) if not val.empty else None
    except Exception:
        return None


# ── Moving average ────────────────────────────────────────────────────────────

def compute_ma(close: pd.Series, length: int = 200) -> Optional[float]:
    """Return latest simple moving average or None if not enough data."""
    if len(close) < length:
        return None
    try:
        return float(close.rolling(window=length).mean().iloc[-1])
    except Exception:
        return None


# ── History (deduplication) ───────────────────────────────────────────────────

def load_history(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_history(path: Path, history: dict) -> None:
    path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def alert_key(symbol: str, ex_date: date) -> str:
    return hashlib.sha1(f"{symbol}:{ex_date}".encode()).hexdigest()[:12]


def already_alerted(history: dict, symbol: str, ex_date: date) -> bool:
    return alert_key(symbol, ex_date) in history


def record_alert(history: dict, symbol: str, ex_date: date, data: dict) -> None:
    history[alert_key(symbol, ex_date)] = {
        "symbol": symbol,
        "ex_date": str(ex_date),
        "alerted_at": datetime.now(tz=timezone.utc).isoformat(),
        **data,
    }


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(token: str, chat_id: str, text: str, logger: logging.Logger) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        if resp.status_code == 200:
            return True
        logger.warning("Telegram API error %s: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False


def build_telegram_message(
    symbol: str,
    ex_date: date,
    rsi: float,
    price: float,
    ma: float,
    days_away: int,
    dividend_yield_pct: Optional[float],
) -> str:
    yield_line = (
        f"Dividend Yield: `{dividend_yield_pct:.2f}%`\n"
        if dividend_yield_pct is not None
        else "Dividend Yield: `N/A`\n"
    )
    low_yield = dividend_yield_pct is not None and dividend_yield_pct < 1.0
    ex_close = days_away < 7
    if low_yield and ex_close:
        grade = "⚠️ LOW YIELD | ⏰ EX-DATE CLOSE"
    elif low_yield:
        grade = "⚠️ LOW YIELD"
    elif ex_close:
        grade = "⏰ EX-DATE CLOSE"
    else:
        grade = "✅ CLEAN"
    return (
        f"*Dividend Quality Pullback Signal*\n"
        f"Ticker: `{symbol}`\n"
        f"Ex-Div Date: `{ex_date}` ({days_away}d away)\n"
        f"{yield_line}"
        f"Price: `${price:.2f}`  |  MA: `${ma:.2f}`\n"
        f"RSI(14): `{rsi:.1f}`\n"
        f"Grade: {grade}"
    )


# ── Rich dashboard ────────────────────────────────────────────────────────────

def build_results_table(results: list[dict], show_all: bool) -> Table:
    table = Table(
        title="Dividend Quality Pullback Scanner — Results",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Symbol", style="bold cyan", no_wrap=True)
    table.add_column("Ex-Date", style="yellow")
    table.add_column("Days", justify="right")
    table.add_column("Yield%", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("MA", justify="right")
    table.add_column("RSI", justify="right")
    table.add_column("Signal", justify="center")
    table.add_column("Reason", overflow="fold")

    for row in results:
        signal_flag = row.get("signal", False)
        if not show_all and not signal_flag:
            continue
        signal_cell = "[green]YES[/green]" if signal_flag else "[dim]no[/dim]"
        table.add_row(
            row["symbol"],
            str(row.get("ex_date") or "N/A"),
            str(row.get("days_away") if row.get("days_away") is not None else "?"),
            fmt_float(row.get("dividend_yield_pct")),
            f"${row['price']:.2f}" if row.get("price") is not None else "N/A",
            f"${row['ma']:.2f}" if row.get("ma") is not None else "N/A",
            f"{row['rsi']:.1f}" if row.get("rsi") is not None else "N/A",
            signal_cell,
            str(row.get("reason_category", "")),
        )
    return table


# ── Audit report ──────────────────────────────────────────────────────────────

def build_report_row(scan_date: date, row: dict) -> dict[str, str]:
    return {
        "scan_date": scan_date.isoformat(),
        "symbol": normalize_report_value(row.get("symbol")),
        "ex_date": normalize_report_value(row.get("ex_date")),
        "days_to_ex_date": normalize_report_value(row.get("days_away")),
        "yf_ex_date": normalize_report_value(row.get("yf_ex_date")),
        "yf_ex_date_source": normalize_report_value(row.get("yf_ex_date_source")),
        "yf_ex_date_error": normalize_report_value(row.get("yf_ex_date_error")),
        "chosen_ex_date": normalize_report_value(row.get("chosen_ex_date")),
        "chosen_ex_date_source": normalize_report_value(row.get("chosen_ex_date_source")),
        "ex_date_match_status": normalize_report_value(row.get("ex_date_match_status")),
        "ex_date_audit_flags": normalize_report_value(row.get("ex_date_audit_flags")),
        "price": normalize_report_value(row.get("price")),
        "ma200": normalize_report_value(row.get("ma")),
        "rsi14": normalize_report_value(row.get("rsi")),
        "dividend_yield_pct": normalize_report_value(row.get("dividend_yield_pct")),
        "signal_passed": "true" if row.get("signal") else "false",
        "reason_category": normalize_report_value(row.get("reason_category")),
        "audit_flags": normalize_report_value(row.get("audit_flags")),
        "passes_audit_min_yield": normalize_report_value(row.get("passes_audit_min_yield")),
        "passes_audit_min_days_to_ex_date": normalize_report_value(row.get("passes_audit_min_days_to_ex_date")),
        "error": normalize_report_value(row.get("error")),
    }


def write_scan_report(
    results: list[dict],
    report_dir: Path,
    scan_date: date,
    logger: logging.Logger,
) -> Optional[Path]:
    """Write per-run CSV audit report. Returns path or None on failure."""
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"scan_report_{scan_date.isoformat()}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS)
            writer.writeheader()
            for row in results:
                writer.writerow(build_report_row(scan_date, row))
        logger.info("Audit report written: %s (%d rows).", path, len(results))
        return path
    except Exception as exc:
        logger.error("Audit report write failed: %s", exc)
        return None


def render_reason_summary(results: list[dict]) -> None:
    counts: dict[str, int] = {}
    for row in results:
        reason = str(row.get("reason_category") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1

    table = Table(
        title="Reason-Count Audit Summary",
        box=box.SIMPLE,
        show_lines=False,
    )
    table.add_column("Reason Category", style="cyan")
    table.add_column("Count", justify="right")

    for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        table.add_row(reason, str(count))

    console.print(table)


# ── Weekend / market-hours guard ──────────────────────────────────────────────

def is_weekend() -> bool:
    return date.today().weekday() >= 5


# ── Row classification ────────────────────────────────────────────────────────

def classify_audit_flags(
    days_away: Optional[int],
    dividend_yield_pct: Optional[float],
    audit_min_yield: float,
    audit_min_days_to_ex_date: int,
    window_days: int,
) -> tuple[str, str, str]:
    flags: list[str] = []

    if days_away is not None and 0 <= days_away <= window_days:
        flags.append("valid_forward_ex_date_in_window")
        if days_away < audit_min_days_to_ex_date:
            flags.append("ex_date_too_close_candidate")

    if dividend_yield_pct is not None and dividend_yield_pct < audit_min_yield:
        flags.append("low_yield_candidate")

    passes_yield = (
        "" if dividend_yield_pct is None
        else ("true" if dividend_yield_pct >= audit_min_yield else "false")
    )
    passes_days = (
        "" if days_away is None
        else ("true" if days_away >= audit_min_days_to_ex_date else "false")
    )

    return "|".join(flags), passes_yield, passes_days


# ── Main scan logic ───────────────────────────────────────────────────────────

def scan(args: argparse.Namespace, logger: logging.Logger) -> None:
    today = date.today()

    console.rule("[bold blue]Dividend Quality Pullback Scanner[/bold blue]")
    console.print(
        f"[dim]Date: {today}  |  Window: {args.window_days}d  |  "
        f"RSI < {args.rsi_threshold}  |  MA({args.ma_length})  |  "
        f"dry-run={'YES' if args.dry_run else 'NO'}[/dim]"
    )
    console.print(
        f"[dim]Audit-only proposed filters: yield >= {args.audit_min_yield:.2f}%  |  "
        f"days_to_ex_date >= {args.audit_min_days_to_ex_date}d[/dim]"
    )

    if not HAS_YFINANCE:
        console.print("[red]yfinance not installed — cannot proceed.[/red]")
        sys.exit(1)

    tickers = fetch_sp500_tickers(logger)
    if args.limit:
        tickers = tickers[: args.limit]
        logger.info("Limiting scan to first %d tickers.", args.limit)

    history = {} if args.dry_run else load_history(HISTORY_FILE)

    results: list[dict] = []
    signals: list[dict] = []

    with console.status("[cyan]Scanning tickers…[/cyan]", spinner="dots") as status:
        for i, symbol in enumerate(tickers, start=1):
            status.update(f"[cyan]({i}/{len(tickers)}) {symbol}[/cyan]")
            logger.debug("Processing %s", symbol)

            row: dict = {
                "symbol": symbol,
                "signal": False,
                "reason_category": "unknown",
                "audit_flags": "",
                "passes_audit_min_yield": "",
                "passes_audit_min_days_to_ex_date": "",
            }

            try:
                ticker_obj = yf.Ticker(symbol)
                info = get_ticker_info(ticker_obj, logger)

                ex_date_details = get_ex_dividend_date_details(
                    ticker_obj,
                    logger,
                    info=info,
                )
                row.update(ex_date_details)
                ex_date = ex_date_details.get("chosen_ex_date")
                if ex_date is None:
                    row["reason_category"] = "no_ex_date_available"
                    logger.debug("%s: no ex-dividend date found.", symbol)
                    results.append(row)
                    time.sleep(args.sleep_seconds)
                    continue

                days_away = (ex_date - today).days
                row["ex_date"] = ex_date
                row["days_away"] = days_away

                if days_away < 0:
                    row["reason_category"] = "stale_or_past_ex_date"
                    logger.debug(
                        "%s: ex_date %s is %d days away (stale/past).",
                        symbol, ex_date, days_away,
                    )
                    results.append(row)
                    time.sleep(args.sleep_seconds)
                    continue

                if days_away > args.window_days:
                    row["reason_category"] = "ex_date_outside_window"
                    logger.debug(
                        "%s: ex_date %s is %d days away (outside window).",
                        symbol, ex_date, days_away,
                    )
                    results.append(row)
                    time.sleep(args.sleep_seconds)
                    continue

                row["reason_category"] = "valid_forward_ex_date_in_window"

                hist_days = max(args.ma_length + 50, 300)
                hist = ticker_obj.history(period=f"{hist_days}d", auto_adjust=True)
                if hist.empty or len(hist) < 20:
                    row["reason_category"] = "yfinance_error"
                    row["error"] = "insufficient_history"
                    logger.debug("%s: insufficient history.", symbol)
                    results.append(row)
                    time.sleep(args.sleep_seconds)
                    continue

                close = hist["Close"].dropna()
                price = float(close.iloc[-1])
                row["price"] = price

                rsi = compute_rsi(close, period=14)
                ma = compute_ma(close, length=args.ma_length)
                dividend_yield_pct = get_dividend_yield_pct(info, price)

                row["rsi"] = rsi
                row["ma"] = ma
                row["dividend_yield_pct"] = dividend_yield_pct

                audit_flags, passes_yield, passes_days = classify_audit_flags(
                    days_away=days_away,
                    dividend_yield_pct=dividend_yield_pct,
                    audit_min_yield=args.audit_min_yield,
                    audit_min_days_to_ex_date=args.audit_min_days_to_ex_date,
                    window_days=args.window_days,
                )
                row["audit_flags"] = audit_flags
                row["passes_audit_min_yield"] = passes_yield
                row["passes_audit_min_days_to_ex_date"] = passes_days

                if rsi is None or rsi >= args.rsi_threshold:
                    row["reason_category"] = "technical_failed_rsi"
                elif ma is None or price <= ma:
                    row["reason_category"] = "technical_failed_ma200"
                else:
                    row["reason_category"] = "signal_generated"
                    row["signal"] = True

                logger.info(
                    "%s | ex=%s (%dd) | yield=%s | price=%.2f | ma=%.2f | "
                    "rsi=%.1f | reason=%s | signal=%s | audit_flags=%s",
                    symbol,
                    ex_date,
                    days_away,
                    fmt_float(dividend_yield_pct),
                    price,
                    ma if ma else 0.0,
                    rsi if rsi else 0.0,
                    row["reason_category"],
                    row["signal"],
                    row["audit_flags"],
                )

                results.append(row)

                if row["signal"]:
                    signals.append(row)

                    if not already_alerted(history, symbol, ex_date):
                        if not args.dry_run and not args.no_telegram:
                            msg = build_telegram_message(
                                symbol=symbol,
                                ex_date=ex_date,
                                rsi=rsi,
                                price=price,
                                ma=ma,
                                days_away=days_away,
                                dividend_yield_pct=dividend_yield_pct,
                            )
                            sent = send_telegram(
                                TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg, logger
                            )
                            logger.info(
                                "Telegram alert for %s: %s",
                                symbol,
                                "sent" if sent else "FAILED",
                            )
                        elif args.dry_run:
                            logger.info("[DRY-RUN] Would send Telegram for %s.", symbol)

                        if not args.dry_run:
                            record_alert(history, symbol, ex_date, {
                                "price": price,
                                "rsi": rsi,
                                "ma": ma,
                                "days_away": days_away,
                                "dividend_yield_pct": dividend_yield_pct,
                            })
                    else:
                        logger.debug("%s already alerted for ex-date %s.", symbol, ex_date)

            except Exception as exc:
                row["reason_category"] = "yfinance_error"
                row["error"] = str(exc)
                results.append(row)
                logger.error("Error processing %s: %s", symbol, exc)

            time.sleep(args.sleep_seconds)

    if not args.dry_run:
        save_history(HISTORY_FILE, history)
        logger.info("History saved (%d entries).", len(history))

    report_path = None
    if args.report and not args.no_report:
        report_path = write_scan_report(
            results=results,
            report_dir=Path(args.report_dir),
            scan_date=today,
            logger=logger,
        )

    display = results if args.show_all else signals
    if display:
        table = build_results_table(display, show_all=True)
        console.print(table)
    else:
        console.print("[yellow]No signals found in this run.[/yellow]")

    render_reason_summary(results)

    console.rule()
    label = "[dim](dry-run)[/dim] " if args.dry_run else ""
    console.print(
        f"{label}Scanned [bold]{len(tickers)}[/bold] tickers  |  "
        f"[green]{len(signals)} signal(s)[/green]"
    )
    if report_path is not None:
        console.print(f"[cyan]Audit report:[/cyan] {report_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dividend_scanner",
        description="Scan S&P 500 for dividend-quality pullback candidates.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run without sending Telegram alerts or writing history.",
    )
    parser.add_argument(
        "--limit", type=int, default=0, metavar="N",
        help="Process only the first N tickers (0 = all).",
    )
    parser.add_argument(
        "--show-all", action="store_true",
        help="Display all scanned tickers in the results table, not just signals.",
    )
    parser.add_argument(
        "--force-weekend", action="store_true",
        help="Run even if today is Saturday or Sunday.",
    )
    parser.add_argument(
        "--no-telegram", action="store_true",
        help="Skip Telegram alerts even when not in dry-run mode.",
    )
    parser.add_argument(
        "--window-days", type=int,
        default=int(os.getenv("WINDOW_DAYS", "21")),
        metavar="DAYS",
        help="Ex-dividend search window in calendar days (default: 21).",
    )
    parser.add_argument(
        "--rsi-threshold", type=float,
        default=float(os.getenv("RSI_THRESHOLD", "38")),
        metavar="RSI",
        help="Maximum RSI value to trigger a signal (default: 38).",
    )
    parser.add_argument(
        "--ma-length", type=int,
        default=int(os.getenv("MA_LENGTH", "200")),
        metavar="PERIODS",
        help="Moving average length in trading days (default: 200).",
    )
    parser.add_argument(
        "--sleep-seconds", type=float,
        default=float(os.getenv("SLEEP_SECONDS", "1")),
        metavar="SEC",
        help="Seconds to sleep between ticker API calls (default: 1).",
    )
    parser.add_argument(
        "--report-dir",
        default=os.getenv("REPORT_DIR", str(PROJECT_ROOT / "reports")),
        help="Directory for CSV audit reports (default: reports/).",
    )
    parser.add_argument(
        "--no-report", action="store_true",
        help="Disable CSV audit report creation.",
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Write a CSV audit report (opt-in). Use --report-dir to set destination.",
    )
    parser.add_argument(
        "--audit-min-yield", type=float,
        default=float(os.getenv("AUDIT_MIN_YIELD", "1.0")),
        metavar="PCT",
        help="Audit-only proposed minimum dividend yield percent (default: 1.0).",
    )
    parser.add_argument(
        "--audit-min-days-to-ex-date", type=int,
        default=int(os.getenv("AUDIT_MIN_DAYS_TO_EX_DATE", "7")),
        metavar="DAYS",
        help="Audit-only proposed minimum days to ex-date (default: 7).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = setup_logging(LOG_FILE)

    logger.info(
        "Scanner started — dry_run=%s limit=%s window=%s rsi_threshold=%s ma=%s",
        args.dry_run,
        args.limit,
        args.window_days,
        args.rsi_threshold,
        args.ma_length,
    )

    if is_weekend() and not args.force_weekend:
        console.print(
            "[yellow]Today is a weekend.  Markets are closed.  "
            "Use --force-weekend to override.[/yellow]"
        )
        logger.info("Exiting early: weekend and --force-weekend not set.")
        sys.exit(0)

    scan(args, logger)


if __name__ == "__main__":
    main()
