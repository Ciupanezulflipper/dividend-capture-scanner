#!/usr/bin/env python3
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tools.run_production_scan import (
    audit_report,
    audit_telegram,
    contains_provider_error,
    discover_fresh_artifact,
    resolve_report_dir,
    snapshot_artifacts,
)


class ProductionRunnerTests(unittest.TestCase):
    def test_resolve_report_dir_supports_both_cli_forms(self) -> None:
        self.assertEqual(
            resolve_report_dir(["--report-dir", "/tmp/a"]), Path("/tmp/a")
        )
        self.assertEqual(
            resolve_report_dir(["--report-dir=/tmp/b"]), Path("/tmp/b")
        )

    def test_provider_markers_cover_observed_dns_and_tls_failures(self) -> None:
        samples = (
            "[Errno 7] No address associated with hostname",
            "NameResolutionError: Failed to resolve api.telegram.org",
            "SSL: CERTIFICATE_VERIFY_FAILED hostname mismatch",
            "Max retries exceeded with url",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(contains_provider_error(sample))

    def test_report_audit_detects_partial_dns_collapse_in_general_error_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan_report.csv"
            fieldnames = [
                "chosen_ex_date",
                "ex_date",
                "price",
                "yf_ex_date_error",
                "error",
                "skip_reason",
                "reason_category",
            ]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for _ in range(90):
                    writer.writerow(
                        {
                            "error": "NameResolutionError: [Errno 7] No address associated with hostname",
                            "reason_category": "yfinance_error",
                        }
                    )
                for _ in range(10):
                    writer.writerow(
                        {
                            "chosen_ex_date": "2026-08-10",
                            "price": "100.00",
                            "reason_category": "technical_failed_rsi",
                        }
                    )

            result = audit_report(path)
            self.assertEqual(result.total_rows, 100)
            self.assertEqual(result.provider_errors, 90)
            self.assertEqual(result.provider_failure_rate, 0.9)
            self.assertTrue(result.is_collapsed)

    def test_unchanged_same_day_artifact_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            path = directory / "scan_health_2026-07-31.json"
            path.write_text("{}", encoding="utf-8")
            before = snapshot_artifacts(directory, "scan_health_*.json")
            self.assertIsNone(
                discover_fresh_artifact(directory, "scan_health_*.json", before)
            )
            path.write_text('{"is_collapsed": false}', encoding="utf-8")
            self.assertEqual(
                discover_fresh_artifact(directory, "scan_health_*.json", before),
                path,
            )

    def test_telegram_false_success_log_is_rejected_when_failure_precedes_it(self) -> None:
        log_delta = "\n".join(
            (
                "Telegram send failed: NameResolutionError",
                "Daily heartbeat sent.",
            )
        )
        result = audit_telegram(
            log_delta,
            ["--daily-heartbeat"],
            scanner_collapsed=False,
            credentials_present=True,
        )
        self.assertTrue(result.heartbeat_claimed)
        self.assertFalse(result.delivery_verified)
        self.assertEqual(result.failure_line_count, 1)

    def test_healthy_heartbeat_requires_credentials_and_no_failure(self) -> None:
        success = audit_telegram(
            "Daily heartbeat sent.",
            ["--daily-heartbeat"],
            scanner_collapsed=False,
            credentials_present=True,
        )
        self.assertTrue(success.delivery_verified)

        missing_credentials = audit_telegram(
            "",
            ["--daily-heartbeat"],
            scanner_collapsed=False,
            credentials_present=False,
        )
        self.assertFalse(missing_credentials.delivery_verified)

    def test_no_signal_no_heartbeat_run_does_not_require_credentials(self) -> None:
        result = audit_telegram(
            "No alerts delivered — history not modified.",
            [],
            scanner_collapsed=False,
            credentials_present=False,
        )
        self.assertFalse(result.delivery_required)
        self.assertTrue(result.delivery_verified)

    def test_dry_run_does_not_require_telegram(self) -> None:
        result = audit_telegram(
            "",
            ["--dry-run", "--daily-heartbeat"],
            scanner_collapsed=False,
            credentials_present=False,
        )
        self.assertFalse(result.delivery_required)
        self.assertTrue(result.delivery_verified)


if __name__ == "__main__":
    unittest.main()
