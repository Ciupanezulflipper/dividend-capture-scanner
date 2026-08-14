#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class QualityScannerIntegrationTests(unittest.TestCase):
    def test_launcher_uses_quality_entry_and_existing_reliability_wrapper(self):
        text = (ROOT / "run_bot.sh").read_text(encoding="utf-8")
        self.assertIn('MAIN_SCRIPT="quality_scanner.py"', text)
        self.assertIn('RUNNER_SCRIPT="tools/run_quality_production_scan.py"', text)

    def test_termux_dependency_policy_preserves_python314_fallback(self):
        launcher = (ROOT / "run_bot.sh").read_text(encoding="utf-8")
        core = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        termux = (ROOT / "requirements-termux.txt").read_text(encoding="utf-8")

        self.assertIn("yfinance==1.4.1", core)
        self.assertNotIn("yfinance>=0.2.66,<0.3", core)
        self.assertIn("numpy==2.5.0", termux)
        self.assertIn("pandas==2.3.1", termux)
        self.assertIn("termux-user-repository.github.io/pypi/", launcher)
        self.assertIn("pip uninstall --break-system-packages -y curl_cffi", launcher)
        self.assertIn('assert yf.__version__ == "1.4.1"', launcher)

    def test_quality_wrapper_reuses_production_runner(self):
        text = (ROOT / "tools" / "run_quality_production_scan.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from tools import run_production_scan as production", text)
        self.assertIn('REPO_ROOT / "quality_scanner.py"', text)

    def test_quality_layer_is_audit_only(self):
        text = (ROOT / "quality_scanner.py").read_text(encoding="utf-8")
        self.assertNotIn("scanner.is_clean_signal =", text)
        self.assertIn("scanner.classify_audit_flags = classify_audit_flags", text)
        self.assertIn("scanner.build_report_row = build_report_row", text)
        self.assertIn("scanner.build_telegram_message = build_telegram_message", text)

    def test_enhanced_message_and_report_fields_without_network(self):
        code = r'''
import json
import sys
import types
from datetime import date

fake = types.ModuleType("dividend_scanner")
fake.REPORT_FIELDS = ["symbol", "signal_passed"]
fake.HAS_YFINANCE = False
fake.yf = types.SimpleNamespace(Ticker=None)
fake.get_ticker_info = lambda ticker, logger: {}
fake.get_ex_dividend_date_details = lambda ticker, logger, info=None: {"chosen_ex_date": date(2026, 8, 14)}
fake.compute_rsi = lambda close, period=14: 32.0
fake.compute_ma = lambda close, length=200: 100.0
fake.get_dividend_yield_pct = lambda info, price: 2.0
fake.classify_audit_flags = lambda *args: ("valid_forward_ex_date_in_window", "true", "true")
fake.build_report_row = lambda scan_date, row: {"symbol": row["symbol"], "signal_passed": "true"}
fake.build_telegram_message = lambda *args, **kwargs: "HEADER\n<b>Status:</b> CLEAN"
fake.normalize_report_value = lambda value: "" if value is None else (value.isoformat() if isinstance(value, date) else str(value))
fake.parse_date_value = lambda value: value if isinstance(value, date) else None
fake.is_clean_signal = lambda flags: "low_yield_candidate" not in flags and "ex_date_too_close_candidate" not in flags
fake.main = lambda: None
sys.modules["dividend_scanner"] = fake

import quality_scanner as quality

quality._quality_by_symbol["TEST"] = {
    "earnings_date": date(2026, 8, 5),
    "days_to_earnings": 4,
    "business_days_to_earnings": 2,
    "earnings_proximity_warning": True,
    "one_day_change_pct": -8.2,
    "abnormal_drop_warning": True,
    "priority_score": 2,
    "priority_grade": "MEDIUM",
}
message = quality.scanner.build_telegram_message(
    symbol="TEST",
    ex_date=date(2026, 8, 14),
    rsi=32.0,
    price=110.0,
    ma=100.0,
    days_away=13,
    dividend_yield_pct=2.0,
    audit_flags="valid_forward_ex_date_in_window|earnings_proximity_warning|abnormal_one_day_drop_warning|priority_medium",
)
report = quality.scanner.build_report_row(date(2026, 8, 1), {"symbol": "TEST"})
print(json.dumps({
    "message": message,
    "report": report,
    "still_clean": quality.scanner.is_clean_signal(
        "valid_forward_ex_date_in_window|earnings_proximity_warning|abnormal_one_day_drop_warning|priority_medium"
    ),
    "fields": quality.scanner.REPORT_FIELDS,
}))
'''
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertIn("Priority:</b> <code>MEDIUM (2/4)</code>", payload["message"])
        self.assertIn("Earnings:</b> <code>Aug 5, 2026</code> ⚠️ CLOSE", payload["message"])
        self.assertIn("Latest daily move:</b> <code>-8.2%</code> ⚠️ ABNORMAL DROP", payload["message"])
        self.assertEqual(payload["report"]["priority_grade"], "MEDIUM")
        self.assertEqual(payload["report"]["earnings_proximity_warning"], "True")
        self.assertEqual(payload["report"]["abnormal_drop_warning"], "True")
        self.assertTrue(payload["still_clean"])
        for field in (
            "earnings_date",
            "one_day_change_pct",
            "priority_score",
            "priority_grade",
        ):
            self.assertIn(field, payload["fields"])


if __name__ == "__main__":
    unittest.main()
