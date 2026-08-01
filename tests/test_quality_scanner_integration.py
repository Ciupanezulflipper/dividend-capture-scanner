#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class QualityScannerIntegrationTests(unittest.TestCase):
    def test_launcher_uses_quality_entry_and_existing_reliability_wrapper(self):
        text = (ROOT / "run_bot.sh").read_text(encoding="utf-8")
        self.assertIn('MAIN_SCRIPT="quality_scanner.py"', text)
        self.assertIn('RUNNER_SCRIPT="tools/run_quality_production_scan.py"', text)

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


if __name__ == "__main__":
    unittest.main()
