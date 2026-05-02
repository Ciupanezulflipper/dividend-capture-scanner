#!/usr/bin/env python3
"""
Dividend Capture Scanner  —  v1 (scanner/alerter only, no trade execution)

Scans S&P 500 for stocks whose ex-dividend date falls within the next
WINDOW_DAYS calendar days and that satisfy entry signal criteria:
  RSI(14) < RSI_THRESHOLD  AND  price > MA(MA_LENGTH)

Sends Telegram alerts and logs results.  Dry-run mode skips Telegram and
history writes.
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from io import StringIO
from typing import Optional

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
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
HISTORY_FILE     = PROJECT_ROOT / os.getenv("HISTORY_FILE", "history.json")
LOG_FILE         = PROJECT_ROOT / os.getenv("LOG_FILE", "stock_scan.log")

SP500_WIKI_URL = (
    "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
)

console = Console()

# ── Logging setup ─────────────────────────────────────────────────────────────

def setup_logging(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("dividend_scanner")
    logger.setLevel(logging.DEBUG)
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
            headers={"User-Agent": "Mozilla/5.0 DividendCaptureScanner/1.0"},
            timeout=30,
        )
        response.raise_for_status()
        tables = pd.read_html(StringIO(response.text), attrs={"id": "constituents"}, flavor="html5lib")
        df = tables[0]
        # Column is 'Symbol' on the Wikipedia table
        col = "Symbol" if "Symbol" in df.columns else df.columns[0]
        tickers = df[col].str.replace(".", "-", regex=False).tolist()
        logger.info("Fetched %d S&P 500 tickers from Wikipedia.", len(tickers))
        return tickers
    except Exception as exc:
        logger.error("Failed to fetch S&P 500 tickers: %s", exc)
        console.print(f"[red]ERROR fetching S&P 500 list: {exc}[/red]")
        sys.exit(1)


# ── Ex-dividend date discovery ────────────────────────────────────────────────

def get_ex_dividend_date(ticker_obj, logger: logging.Logger) -> Optional[date]:
    """Try yfinance .calendar first, then .info for exDividendDate."""
    symbol = ticker_obj.ticker

    # Method 1: calendar (returns a dict keyed by event name)
    try:
        cal = ticker_obj.calendar
        if cal is not None:
            # newer yfinance: cal is a dict
            if isinstance(cal, dict):
                ex_raw = cal.get("Ex-Dividend Date") or cal.get("exDividendDate")
                if ex_raw:
                    if isinstance(ex_raw, (date, datetime)):
                        return ex_raw.date() if isinstance(ex_raw, datetime) else ex_raw
                    return pd.Timestamp(ex_raw).date()
            # older yfinance: cal is a DataFrame with dates as columns
            elif isinstance(cal, pd.DataFrame):
                if "Ex-Dividend Date" in cal.index:
                    val = cal.loc["Ex-Dividend Date"].iloc[0]
                    return pd.Timestamp(val).date()
    except Exception as exc:
        logger.debug("%s calendar error: %s", symbol, exc)

    # Method 2: info dict
    try:
        info = ticker_obj.info
        ex_ts = info.get("exDividendDate")
        if ex_ts:
            # yfinance returns Unix timestamp (int/float)
            if isinstance(ex_ts, (int, float)):
                return datetime.fromtimestamp(ex_ts, tz=timezone.utc).date()
            return pd.Timestamp(ex_ts).date()
    except Exception as exc:
        logger.debug("%s info error: %s", symbol, exc)

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


def build_telegram_message(symbol: str, ex_date: date, rsi: float, price: float,
                            ma: float, days_away: int) -> str:
    return (
        f"*Dividend Capture Signal*\n"
        f"Ticker: `{symbol}`\n"
        f"Ex-Div Date: `{ex_date}` ({days_away}d away)\n"
        f"Price: `${price:.2f}`  |  MA{'' }: `${ma:.2f}`\n"
        f"RSI(14): `{rsi:.1f}`"
    )


# ── Rich dashboard ────────────────────────────────────────────────────────────

def build_results_table(results: list[dict], show_all: bool) -> Table:
    table = Table(
        title="Dividend Capture Scanner — Results",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("Symbol",    style="bold cyan",   no_wrap=True)
    table.add_column("Ex-Date",   style="yellow")
    table.add_column("Days Away", justify="right")
    table.add_column("Price",     justify="right")
    table.add_column("MA",        justify="right")
    table.add_column("RSI(14)",   justify="right")
    table.add_column("Signal",    justify="center")

    for r in results:
        signal_flag = r.get("signal", False)
        if not show_all and not signal_flag:
            continue
        signal_cell = "[green]YES[/green]" if signal_flag else "[dim]no[/dim]"
        rsi_val = r.get("rsi")
        ma_val  = r.get("ma")
        price   = r.get("price")
        table.add_row(
            r["symbol"],
            str(r.get("ex_date", "N/A")),
            str(r.get("days_away", "?")),
            f"${price:.2f}"   if price  is not None else "N/A",
            f"${ma_val:.2f}"  if ma_val is not None else "N/A",
            f"{rsi_val:.1f}"  if rsi_val is not None else "N/A",
            signal_cell,
        )
    return table


# ── Weekend / market-hours guard ──────────────────────────────────────────────

def is_weekend() -> bool:
    return date.today().weekday() >= 5


# ── Main scan logic ───────────────────────────────────────────────────────────

def scan(args: argparse.Namespace, logger: logging.Logger) -> None:
    today     = date.today()
    cutoff    = today + timedelta(days=args.window_days)

    console.rule("[bold blue]Dividend Capture Scanner[/bold blue]")
    console.print(
        f"[dim]Date: {today}  |  Window: {args.window_days}d  |  "
        f"RSI < {args.rsi_threshold}  |  MA({args.ma_length})  |  "
        f"dry-run={'YES' if args.dry_run else 'NO'}[/dim]"
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

            row: dict = {"symbol": symbol, "signal": False}

            try:
                tk = yf.Ticker(symbol)

                # ── Ex-dividend date ─────────────────────────────────────────
                ex_date = get_ex_dividend_date(tk, logger)
                if ex_date is None:
                    logger.debug("%s: no ex-dividend date found.", symbol)
                    if args.show_all:
                        row["ex_date"] = None
                        row["days_away"] = None
                        results.append(row)
                    time.sleep(args.sleep_seconds)
                    continue

                days_away = (ex_date - today).days
                row["ex_date"]   = ex_date
                row["days_away"] = days_away

                if not (0 <= days_away <= args.window_days):
                    logger.debug("%s: ex_date %s is %d days away (outside window).",
                                 symbol, ex_date, days_away)
                    if args.show_all:
                        results.append(row)
                    time.sleep(args.sleep_seconds)
                    continue

                # ── Historical price data ────────────────────────────────────
                hist_days = max(args.ma_length + 50, 300)
                hist = tk.history(period=f"{hist_days}d", auto_adjust=True)
                if hist.empty or len(hist) < 20:
                    logger.debug("%s: insufficient history.", symbol)
                    if args.show_all:
                        results.append(row)
                    time.sleep(args.sleep_seconds)
                    continue

                close = hist["Close"].dropna()
                price = float(close.iloc[-1])
                row["price"] = price

                # ── Indicators ───────────────────────────────────────────────
                rsi = compute_rsi(close, period=14)
                ma  = compute_ma(close, length=args.ma_length)
                row["rsi"] = rsi
                row["ma"]  = ma

                # ── Signal filter ────────────────────────────────────────────
                signal = (
                    rsi is not None
                    and ma is not None
                    and rsi < args.rsi_threshold
                    and price > ma
                )
                row["signal"] = signal

                logger.info(
                    "%s | ex=%s (%dd) | price=%.2f | ma=%.2f | rsi=%.1f | signal=%s",
                    symbol, ex_date, days_away, price,
                    ma if ma else 0.0,
                    rsi if rsi else 0.0,
                    signal,
                )

                results.append(row)

                if signal:
                    signals.append(row)

                    # ── Deduplication + alert ────────────────────────────────
                    if not already_alerted(history, symbol, ex_date):
                        if not args.dry_run and not args.no_telegram:
                            msg = build_telegram_message(
                                symbol, ex_date, rsi, price, ma, days_away
                            )
                            sent = send_telegram(
                                TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg, logger
                            )
                            logger.info("Telegram alert for %s: %s", symbol,
                                        "sent" if sent else "FAILED")
                        elif args.dry_run:
                            logger.info("[DRY-RUN] Would send Telegram for %s.", symbol)

                        if not args.dry_run:
                            record_alert(history, symbol, ex_date, {
                                "price": price, "rsi": rsi, "ma": ma,
                                "days_away": days_away,
                            })
                    else:
                        logger.debug("%s already alerted for ex-date %s.", symbol, ex_date)

            except Exception as exc:
                logger.error("Error processing %s: %s", symbol, exc)

            time.sleep(args.sleep_seconds)

    # ── Persist history ───────────────────────────────────────────────────────
    if not args.dry_run:
        save_history(HISTORY_FILE, history)
        logger.info("History saved (%d entries).", len(history))

    # ── Rich output ───────────────────────────────────────────────────────────
    display = results if args.show_all else signals
    if display:
        table = build_results_table(display, show_all=True)
        console.print(table)
    else:
        console.print("[yellow]No signals found in this run.[/yellow]")

    console.rule()
    label = "[dim](dry-run)[/dim] " if args.dry_run else ""
    console.print(
        f"{label}Scanned [bold]{len(tickers)}[/bold] tickers  |  "
        f"[green]{len(signals)} signal(s)[/green]"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dividend_scanner",
        description="Scan S&P 500 for near-term ex-dividend + RSI entry signals.",
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
    return parser.parse_args()


def main() -> None:
    args   = parse_args()
    logger = setup_logging(LOG_FILE)

    logger.info(
        "Scanner started — dry_run=%s limit=%s window=%s rsi_threshold=%s ma=%s",
        args.dry_run, args.limit, args.window_days, args.rsi_threshold, args.ma_length,
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
