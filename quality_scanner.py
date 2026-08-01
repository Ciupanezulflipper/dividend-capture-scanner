#!/usr/bin/env python3
"""Audit-only signal-quality layer over the proven DQP scanner."""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import date
from typing import Any, Optional

import dividend_scanner as scanner
from signal_quality_audit import (
    abnormal_drop_warning,
    append_quality_flags,
    earnings_audit,
    extract_earnings_date,
    latest_one_day_change_pct,
    priority_audit,
)

QUALITY_REPORT_FIELDS = [
    "earnings_date",
    "days_to_earnings",
    "business_days_to_earnings",
    "earnings_proximity_warning",
    "one_day_change_pct",
    "abnormal_drop_warning",
    "priority_score",
    "priority_grade",
]
ABNORMAL_DROP_THRESHOLD_PCT = float(os.getenv("AUDIT_ABNORMAL_DROP_PCT", "7.0"))
EARNINGS_PROXIMITY_BUSINESS_DAYS = int(
    os.getenv("AUDIT_EARNINGS_PROXIMITY_BUSINESS_DAYS", "5")
)

_current: dict[str, Any] = {}
_quality_by_symbol: dict[str, dict[str, Any]] = {}
_installed = False
_originals: dict[str, Any] = {}


def _reset(symbol: str) -> None:
    _current.clear()
    _current.update(
        {
            "symbol": symbol,
            "info": {},
            "earnings_date": None,
            "one_day_change_pct": None,
            "abnormal_drop_warning": False,
            "rsi": None,
            "ma": None,
            "price": None,
            "dividend_yield_pct": None,
        }
    )


class _TickerProxy:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._calendar_loaded = False
        self._calendar_value: Any = None
        self.ticker = getattr(inner, "ticker", _current.get("symbol", "UNKNOWN"))

    @property
    def calendar(self) -> Any:
        if not self._calendar_loaded:
            self._calendar_value = self._inner.calendar
            self._calendar_loaded = True
        return self._calendar_value

    def history(self, *args: Any, **kwargs: Any) -> Any:
        history = self._inner.history(*args, **kwargs)
        try:
            close = history["Close"].dropna()
            change = latest_one_day_change_pct(close.tolist())
        except (KeyError, TypeError, AttributeError):
            change = None
        _current["one_day_change_pct"] = change
        _current["abnormal_drop_warning"] = abnormal_drop_warning(
            change, ABNORMAL_DROP_THRESHOLD_PCT
        )
        return history

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _quality_for(symbol: str) -> dict[str, Any]:
    return _quality_by_symbol.get(symbol, {})


def _format_date(value: Any) -> str:
    return value.strftime("%b %-d, %Y") if isinstance(value, date) else "N/A"


def install_quality_layer() -> None:
    global _installed
    if _installed:
        return
    _installed = True

    for field in reversed(QUALITY_REPORT_FIELDS):
        if field not in scanner.REPORT_FIELDS:
            insert_at = scanner.REPORT_FIELDS.index("signal_passed")
            scanner.REPORT_FIELDS.insert(insert_at, field)

    _originals.update(
        {
            "ticker_factory": scanner.yf.Ticker if scanner.HAS_YFINANCE else None,
            "get_ticker_info": scanner.get_ticker_info,
            "get_ex_dividend_date_details": scanner.get_ex_dividend_date_details,
            "compute_rsi": scanner.compute_rsi,
            "compute_ma": scanner.compute_ma,
            "get_dividend_yield_pct": scanner.get_dividend_yield_pct,
            "classify_audit_flags": scanner.classify_audit_flags,
            "build_report_row": scanner.build_report_row,
            "build_telegram_message": scanner.build_telegram_message,
        }
    )

    if scanner.HAS_YFINANCE:
        def ticker_factory(symbol: str, *args: Any, **kwargs: Any) -> _TickerProxy:
            _reset(symbol)
            return _TickerProxy(_originals["ticker_factory"](symbol, *args, **kwargs))

        scanner.yf.Ticker = ticker_factory

    def get_ticker_info(ticker_obj: Any, logger: Any) -> dict[str, Any]:
        info = _originals["get_ticker_info"](ticker_obj, logger)
        _current["info"] = info
        return info

    def get_ex_dividend_date_details(
        ticker_obj: Any,
        logger: Any,
        info: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        details = _originals["get_ex_dividend_date_details"](
            ticker_obj, logger, info=info
        )
        try:
            calendar = ticker_obj.calendar
        except Exception:
            calendar = None
        earnings_date = extract_earnings_date(
            calendar,
            info or _current.get("info", {}),
            scanner.parse_date_value,
            date.today(),
        )
        _current["earnings_date"] = earnings_date
        _current["ex_date"] = details.get("chosen_ex_date")
        return details

    def compute_rsi(close: Any, period: int = 14) -> Optional[float]:
        value = _originals["compute_rsi"](close, period=period)
        _current["rsi"] = value
        return value

    def compute_ma(close: Any, length: int = 200) -> Optional[float]:
        value = _originals["compute_ma"](close, length=length)
        _current["ma"] = value
        return value

    def get_dividend_yield_pct(
        info: dict[str, Any], price: Optional[float]
    ) -> Optional[float]:
        value = _originals["get_dividend_yield_pct"](info, price)
        _current["price"] = price
        _current["dividend_yield_pct"] = value
        return value

    def classify_audit_flags(
        days_away: Optional[int],
        dividend_yield_pct: Optional[float],
        audit_min_yield: float,
        audit_min_days_to_ex_date: int,
        window_days: int,
    ) -> tuple[str, str, str]:
        base_flags, passes_yield, passes_days = _originals["classify_audit_flags"](
            days_away,
            dividend_yield_pct,
            audit_min_yield,
            audit_min_days_to_ex_date,
            window_days,
        )
        ex_date = _current.get("ex_date")
        earnings = earnings_audit(
            date.today(),
            ex_date if isinstance(ex_date, date) else date.today(),
            _current.get("earnings_date"),
            EARNINGS_PROXIMITY_BUSINESS_DAYS,
        )
        priority = priority_audit(
            rsi=_current.get("rsi"),
            dividend_yield_pct=dividend_yield_pct,
            price=_current.get("price"),
            ma=_current.get("ma"),
            days_away=days_away,
            earnings_warning=earnings["earnings_proximity_warning"],
            abnormal_drop=bool(_current.get("abnormal_drop_warning")),
        )
        quality = {
            **earnings,
            "one_day_change_pct": _current.get("one_day_change_pct"),
            "abnormal_drop_warning": bool(_current.get("abnormal_drop_warning")),
            **priority,
        }
        symbol = str(_current.get("symbol") or "")
        if symbol:
            _quality_by_symbol[symbol] = deepcopy(quality)
        flags = append_quality_flags(
            base_flags,
            earnings_warning=earnings["earnings_proximity_warning"],
            abnormal_drop=quality["abnormal_drop_warning"],
            priority_grade=priority["priority_grade"],
        )
        return flags, passes_yield, passes_days

    def build_report_row(scan_date: date, row: dict[str, Any]) -> dict[str, str]:
        output = _originals["build_report_row"](scan_date, row)
        quality = _quality_for(str(row.get("symbol") or ""))
        for field in QUALITY_REPORT_FIELDS:
            output[field] = scanner.normalize_report_value(quality.get(field))
        return output

    def build_telegram_message(*args: Any, **kwargs: Any) -> str:
        message = _originals["build_telegram_message"](*args, **kwargs)
        symbol = kwargs.get("symbol") if "symbol" in kwargs else args[0]
        quality = _quality_for(str(symbol))
        grade = quality.get("priority_grade", "N/A")
        score = quality.get("priority_score")
        priority = f"{grade} ({score}/4)" if score is not None else "N/A"
        earnings_date = _format_date(quality.get("earnings_date"))
        earnings_suffix = (
            " ⚠️ CLOSE" if quality.get("earnings_proximity_warning") else ""
        )
        move = quality.get("one_day_change_pct")
        move_text = f"{move:+.1f}%" if isinstance(move, (int, float)) else "N/A"
        move_suffix = " ⚠️ ABNORMAL DROP" if quality.get("abnormal_drop_warning") else ""
        extra = (
            f"<b>Priority:</b> <code>{priority}</code>\n"
            f"<b>Earnings:</b> <code>{earnings_date}</code>{earnings_suffix}\n"
            f"<b>Latest daily move:</b> <code>{move_text}</code>{move_suffix}\n"
        )
        marker = "<b>Status:</b>"
        return message.replace(marker, extra + marker, 1)

    scanner.get_ticker_info = get_ticker_info
    scanner.get_ex_dividend_date_details = get_ex_dividend_date_details
    scanner.compute_rsi = compute_rsi
    scanner.compute_ma = compute_ma
    scanner.get_dividend_yield_pct = get_dividend_yield_pct
    scanner.classify_audit_flags = classify_audit_flags
    scanner.build_report_row = build_report_row
    scanner.build_telegram_message = build_telegram_message


install_quality_layer()

if __name__ == "__main__":
    scanner.main()
