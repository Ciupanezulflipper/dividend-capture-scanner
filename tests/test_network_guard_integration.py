#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from telegram_delivery import TelegramDeliveryResult
from tools.network_preflight import PreflightResult, ProbeResult
from tools.runtime_monitor import MonitorPublishResult
from tools import run_quality_production_scan as guarded


class NetworkGuardIntegrationTests(unittest.TestCase):
    def passing_preflight(self) -> PreflightResult:
        return PreflightResult(
            attempted=True,
            passed=True,
            attempts=1,
            max_attempts=7,
            waited_seconds=0,
            recovered_during_retry=False,
            results=(
                ProbeResult("yahoo_chart", True, True, 200, "ok"),
                ProbeResult("telegram_getme", True, True, 200, "ok"),
            ),
        )

    def failing_preflight(self) -> PreflightResult:
        return PreflightResult(
            attempted=True,
            passed=False,
            attempts=7,
            max_attempts=7,
            waited_seconds=1_800,
            recovered_during_retry=False,
            results=(
                ProbeResult("yahoo_chart", True, False, None, "DNS failed"),
                ProbeResult("telegram_getme", True, False, None, "DNS failed"),
            ),
        )

    def test_dry_run_never_waits_on_network_preflight(self) -> None:
        with patch.object(guarded, "_enabled", return_value=True):
            self.assertFalse(guarded.network_preflight_required(["--dry-run"]))
            self.assertTrue(guarded.network_preflight_required([]))

    def test_preflight_failure_writes_truthful_health_without_scanner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "reports"
            outage = root / ".runtime" / "network_outage.json"
            started = datetime(2026, 8, 6, 14, 0, tzinfo=timezone.utc)
            monitor = MonitorPublishResult(False, False, False, "disabled")

            with (
                patch.object(guarded, "OUTAGE_STATE_FILE", outage),
                patch.object(guarded, "_current_scan_date", return_value="2026-08-06"),
                patch.object(guarded, "_publish", return_value=monitor),
            ):
                code = guarded.write_preflight_failure(
                    ["--report", "--report-dir", str(report_dir)],
                    self.failing_preflight(),
                    started,
                )

            self.assertEqual(code, 25)
            health = report_dir / "run_health_2026-08-06.json"
            payload = json.loads(health.read_text(encoding="utf-8"))
            self.assertFalse(payload["success"])
            self.assertIsNone(payload["scanner_exit_code"])
            self.assertEqual(payload["failure_reasons"], ["network_preflight_failed"])
            self.assertEqual(payload["network_preflight"]["attempts"], 7)
            self.assertTrue(outage.exists())

    def test_recovery_notice_clears_state_only_after_verified_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "outage.json"
            state.write_text("{}", encoding="utf-8")
            logger = logging.getLogger("test-recovery")
            logger.handlers.clear()
            logger.addHandler(logging.NullHandler())
            delivery = TelegramDeliveryResult(
                kind="network_recovery",
                subject="2026-08-06T14:00:00+00:00",
                required=False,
                attempted=True,
                delivered=True,
                outcome="delivered",
                status_code=200,
            )
            with (
                patch.object(guarded, "OUTAGE_STATE_FILE", state),
                patch.object(guarded, "_env_value", side_effect=lambda key, default="": {"TELEGRAM_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"}.get(key, default)),
                patch.object(guarded, "_recovery_logger", return_value=logger),
                patch.object(guarded, "send_telegram", return_value=delivery),
            ):
                result = guarded.send_recovery_notice(
                    {"first_failure_utc": "2026-08-06T14:00:00+00:00"}
                )

            self.assertTrue(result and result.delivered)
            self.assertFalse(state.exists())

    def test_enriches_base_health_with_preflight_and_monitor_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            health = report_dir / "run_health_2026-08-06.json"
            health.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "scan_date": "2026-08-06",
                        "finished_at_utc": "2026-08-06T14:10:00+00:00",
                        "duration_seconds": 600,
                        "failure_reasons": [],
                        "warnings": [],
                        "success": True,
                    }
                ),
                encoding="utf-8",
            )
            monitor = MonitorPublishResult(
                True, True, True, "delivered", status_code=200
            )
            with (
                patch.object(guarded, "_current_scan_date", return_value="2026-08-06"),
                patch.object(guarded, "_publish", return_value=monitor),
            ):
                guarded.enrich_run_health(
                    ["--report-dir", str(report_dir)],
                    self.passing_preflight(),
                    None,
                    0,
                )

            payload = json.loads(health.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 2)
            self.assertTrue(payload["network_preflight"]["passed"])
            self.assertTrue(payload["runtime_monitor"]["delivered"])

    def test_failed_preflight_prevents_base_scanner_execution(self) -> None:
        failure = self.failing_preflight()
        with (
            patch.object(guarded, "execute_preflight", return_value=failure),
            patch.object(guarded, "write_preflight_failure", return_value=25) as write,
            patch.object(guarded.production, "run") as production_run,
        ):
            code = guarded.run(["--report"])

        self.assertEqual(code, 25)
        write.assert_called_once()
        production_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
