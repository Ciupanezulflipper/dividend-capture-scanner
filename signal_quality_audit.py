#!/usr/bin/env python3
"""Small, provider-free quality annotations for DQP candidates."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Callable, Mapping, Optional

EARNINGS_CALENDAR_KEYS = (
    "Earnings Date",
    "EarningsDate",
    "earningsDate",
    "earnings_date",
)
EARNINGS_INFO_KEYS = (
    "earningsTimestamp",
    "earningsTimestampStart",
    "earningsTimestampEnd",
)


def _calendar_value(calendar: Any, key: str) -> Any:
    if isinstance(calendar, Mapping):
        return calendar.get(key)
    try:
        if key in calendar.index:
            value = calendar.loc[key]
            try:
                return value.iloc[0]
            except (AttributeError, IndexError, KeyError):
                return value
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    try:
        if key in calendar:
            return calendar[key]
    except (KeyError, TypeError, ValueError):
        pass
    return None


def extract_earnings_date(
    calendar: Any,
    info: Mapping[str, Any] | None,
    parse_date: Callable[[Any], Optional[date]],
    today: date,
) -> Optional[date]:
    """Return the nearest non-past earnings date from existing yfinance data."""
    candidates: list[date] = []
    for key in EARNINGS_CALENDAR_KEYS:
        parsed = parse_date(_calendar_value(calendar, key))
        if parsed is not None:
            candidates.append(parsed)
    for key in EARNINGS_INFO_KEYS:
        parsed = parse_date((info or {}).get(key))
        if parsed is not None:
            candidates.append(parsed)
    future = sorted(item for item in candidates if item >= today)
    return future[0] if future else None


def business_days_until(start: date, end: date) -> int:
    """Count weekdays after start through end; holidays are intentionally ignored."""
    if end == start:
        return 0
    direction = 1 if end > start else -1
    cursor = start
    count = 0
    while cursor != end:
        cursor += timedelta(days=direction)
        if cursor.weekday() < 5:
            count += direction
    return count


def earnings_audit(
    today: date,
    ex_date: date,
    earnings_date: Optional[date],
    max_business_days: int = 5,
) -> dict[str, Any]:
    if earnings_date is None:
        return {
            "earnings_date": None,
            "days_to_earnings": None,
            "business_days_to_earnings": None,
            "earnings_proximity_warning": False,
        }
    calendar_days = (earnings_date - today).days
    business_days = business_days_until(today, earnings_date)
    upcoming = earnings_date >= today
    warning = upcoming and (
        business_days <= max_business_days or earnings_date <= ex_date
    )
    return {
        "earnings_date": earnings_date,
        "days_to_earnings": calendar_days,
        "business_days_to_earnings": business_days,
        "earnings_proximity_warning": warning,
    }


def latest_one_day_change_pct(close_values: Any) -> Optional[float]:
    """Return the latest close-to-close percentage move."""
    try:
        values = [float(value) for value in close_values if math.isfinite(float(value))]
    except (TypeError, ValueError):
        return None
    if len(values) < 2 or values[-2] <= 0:
        return None
    return ((values[-1] / values[-2]) - 1.0) * 100.0


def abnormal_drop_warning(
    one_day_change_pct: Optional[float],
    threshold_pct: float = 7.0,
) -> bool:
    return (
        one_day_change_pct is not None
        and one_day_change_pct <= -abs(threshold_pct)
    )


def priority_audit(
    *,
    rsi: Optional[float],
    dividend_yield_pct: Optional[float],
    price: Optional[float],
    ma: Optional[float],
    days_away: Optional[int],
    earnings_warning: bool,
    abnormal_drop: bool,
) -> dict[str, Any]:
    """Produce a transparent 0-4 audit score without changing signal eligibility."""
    score = 0
    if rsi is not None and rsi <= 35:
        score += 1
    if dividend_yield_pct is not None and dividend_yield_pct >= 1.5:
        score += 1
    if price is not None and ma is not None and ma > 0 and price >= ma * 1.03:
        score += 1
    if days_away is not None and 7 <= days_away <= 21:
        score += 1
    if earnings_warning:
        score -= 1
    if abnormal_drop:
        score -= 1
    score = max(0, min(4, score))
    grade = "HIGH" if score >= 3 else ("MEDIUM" if score == 2 else "LOW")
    return {"priority_score": score, "priority_grade": grade}


def append_quality_flags(
    base_flags: str,
    *,
    earnings_warning: bool,
    abnormal_drop: bool,
    priority_grade: str,
) -> str:
    flags = [flag for flag in str(base_flags or "").split("|") if flag]
    if earnings_warning:
        flags.append("earnings_proximity_warning")
    if abnormal_drop:
        flags.append("abnormal_one_day_drop_warning")
    flags.append(f"priority_{priority_grade.lower()}")
    return "|".join(dict.fromkeys(flags))
