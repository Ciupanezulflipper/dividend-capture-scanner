#!/usr/bin/env python3
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from signal_quality_audit import (
    abnormal_drop_warning,
    append_quality_flags,
    business_days_until,
    earnings_audit,
    extract_earnings_date,
    latest_one_day_change_pct,
    priority_audit,
)


def parse_date(value):
    if isinstance(value, date):
        return value
    if isinstance(value, (list, tuple)):
        return parse_date(value[0]) if value else None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date()
    return None


class SignalQualityAuditTests(unittest.TestCase):
    def test_extracts_nearest_future_calendar_earnings_date(self):
        found = extract_earnings_date(
            {"Earnings Date": [date(2026, 8, 7), date(2026, 8, 8)]},
            {},
            parse_date,
            date(2026, 8, 1),
        )
        self.assertEqual(found, date(2026, 8, 7))

    def test_uses_info_timestamp_fallback(self):
        stamp = datetime(2026, 8, 10, tzinfo=timezone.utc).timestamp()
        found = extract_earnings_date(
            {}, {"earningsTimestampStart": stamp}, parse_date, date(2026, 8, 1)
        )
        self.assertEqual(found, date(2026, 8, 10))

    def test_business_days_ignore_weekend(self):
        self.assertEqual(
            business_days_until(date(2026, 7, 31), date(2026, 8, 3)), 1
        )

    def test_earnings_warning_before_ex_date(self):
        result = earnings_audit(
            date(2026, 8, 1), date(2026, 8, 20), date(2026, 8, 12), 5
        )
        self.assertTrue(result["earnings_proximity_warning"])

    def test_earnings_after_ex_and_not_close_is_not_warning(self):
        result = earnings_audit(
            date(2026, 8, 1), date(2026, 8, 7), date(2026, 8, 20), 5
        )
        self.assertFalse(result["earnings_proximity_warning"])

    def test_latest_one_day_change_and_drop_warning(self):
        change = latest_one_day_change_pct([100.0, 92.0])
        self.assertAlmostEqual(change, -8.0)
        self.assertTrue(abnormal_drop_warning(change, 7.0))
        self.assertFalse(abnormal_drop_warning(-6.9, 7.0))

    def test_priority_is_high_for_strong_clean_profile(self):
        result = priority_audit(
            rsi=32,
            dividend_yield_pct=2.1,
            price=110,
            ma=100,
            days_away=12,
            earnings_warning=False,
            abnormal_drop=False,
        )
        self.assertEqual(result, {"priority_score": 4, "priority_grade": "HIGH"})

    def test_risk_warnings_reduce_priority_but_do_not_reject(self):
        result = priority_audit(
            rsi=32,
            dividend_yield_pct=2.1,
            price=110,
            ma=100,
            days_away=12,
            earnings_warning=True,
            abnormal_drop=True,
        )
        self.assertEqual(result, {"priority_score": 2, "priority_grade": "MEDIUM"})

    def test_append_quality_flags_preserves_existing_filters(self):
        flags = append_quality_flags(
            "valid_forward_ex_date_in_window|low_yield_candidate",
            earnings_warning=True,
            abnormal_drop=False,
            priority_grade="LOW",
        )
        self.assertEqual(
            flags,
            "valid_forward_ex_date_in_window|low_yield_candidate|"
            "earnings_proximity_warning|priority_low",
        )


if __name__ == "__main__":
    unittest.main()
