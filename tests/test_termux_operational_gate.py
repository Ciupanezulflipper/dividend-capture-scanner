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
from tools.termux_gate_core import (
    atomic_json,
    cron_audit,
    history_pair,
    parse_crontab,
    redact,
)
from tools.termux_gate_runtime import boot_audit, latest_health, timezone_audit
from tools.termux_operational_gate import (
    canary,
    canary_status,
    overall,
    result_code,
)


class Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.status_code = status
        self.payload = payload
        self.text = json.dumps(payload)

    def json(self) -> object:
        return self.payload


class OperationalGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.repo = self.home / "dividend-capture-scanner"
        self.repo.mkdir()
        (self.repo / "run_bot.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_history(self, *, different_bytes: bool = False) -> None:
        payload = {
            "AAPL:2026-08-07": {"symbol": "AAPL"},
            "MSFT:2026-08-14": {"symbol": "MSFT"},
        }
        primary = json.dumps(payload, indent=2)
        backup = (
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if different_bytes
            else primary
        )
        (self.repo / "history.json").write_text(primary, encoding="utf-8")
        (self.repo / "history.json.last-good").write_text(backup, encoding="utf-8")

    def test_redact_hides_assignment_and_bot_url(self) -> None:
        output = redact("TELEGRAM_TOKEN=secret /botother-secret/sendMessage")
        self.assertNotIn("secret", output)
        self.assertIn("[REDACTED]", output)

    def test_parse_crontab_keeps_zone_and_entry(self) -> None:
        variables, entries = parse_crontab(
            "CRON_TZ=UTC\n"
            "0 10 * * 1-5 cd /tmp/app && ./run_bot.sh --daily-heartbeat\n"
        )
        self.assertEqual(variables["CRON_TZ"], "UTC")
        self.assertEqual(entries[0][0], "0 10 * * 1-5")

    def test_cron_audit_matches_path_schedule_and_args(self) -> None:
        text = (
            "CRON_TZ=UTC\n"
            f"0 10 * * 1-5 {self.repo}/run_bot.sh --daily-heartbeat --report\n"
        )
        result, variables = cron_audit(
            self.repo,
            "0 10 * * 1-5",
            ["--daily-heartbeat", "--report"],
            lambda _: (0, text, ""),
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(variables["CRON_TZ"], "UTC")

    def test_cron_audit_detects_missing_required_arg(self) -> None:
        text = f"0 10 * * 1-5 {self.repo}/run_bot.sh --report\n"
        result, _ = cron_audit(
            self.repo,
            "0 10 * * 1-5",
            ["--daily-heartbeat"],
            lambda _: (0, text, ""),
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertIn(
            "missing_arg=--daily-heartbeat",
            result["evidence"]["entries"][0]["reasons"],
        )

    def test_timezone_prefers_explicit_cron_zone(self) -> None:
        result = timezone_audit(
            "UTC",
            {"CRON_TZ": "UTC"},
            lambda _: (127, "", "unused"),
        )
        self.assertEqual(result["status"], "PASS")

    def test_timezone_detects_android_mismatch(self) -> None:
        result = timezone_audit(
            "America/New_York", {}, lambda _: (0, "Europe/Bucharest\n", "")
        )
        self.assertEqual(result["status"], "FAIL")

    def test_boot_comments_do_not_count(self) -> None:
        directory = self.home / ".termux" / "boot"
        directory.mkdir(parents=True)
        (directory / "comments.sh").write_text(
            "# crond\n# termux-wake-lock\n", encoding="utf-8"
        )
        self.assertEqual([item["status"] for item in boot_audit(self.home)], ["FAIL", "FAIL"])

    def test_boot_commands_pass(self) -> None:
        directory = self.home / ".termux" / "boot"
        directory.mkdir(parents=True)
        (directory / "start.sh").write_text(
            "termux-wake-lock\npgrep crond || crond\n", encoding="utf-8"
        )
        self.assertEqual([item["status"] for item in boot_audit(self.home)], ["PASS", "PASS"])

    def test_history_pair_accepts_semantic_equality_with_different_bytes(self) -> None:
        self.write_history(different_bytes=True)
        result, hashes = history_pair(self.repo)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["evidence"]["semantic_equal"])
        self.assertFalse(result["evidence"]["byte_equal"])
        self.assertNotEqual(hashes["primary"], hashes["backup"])

    def test_history_pair_rejects_semantic_difference(self) -> None:
        self.write_history()
        (self.repo / "history.json.last-good").write_text("{}", encoding="utf-8")
        result, _ = history_pair(self.repo)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["evidence"]["semantic_equal"])

    def test_latest_health_finds_nested_report(self) -> None:
        directory = self.repo / "reports" / "us_market_20260801"
        directory.mkdir(parents=True)
        path = directory / "run_health_2026-08-01.json"
        path.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
        result = latest_health(self.repo)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["evidence"]["path"], str(path))

    def test_canary_success_keeps_each_history_file_unchanged(self) -> None:
        self.write_history(different_bytes=True)
        before = history_pair(self.repo)[1]
        captured = {}

        def post(url, json, timeout):
            captured["text"] = json["text"]
            return Response({"ok": True, "result": {"message_id": 1}})

        logger = logging.getLogger("canary-pass")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        with patch.dict(
            "os.environ",
            {"TELEGRAM_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "-100123"},
            clear=False,
        ):
            result, delivery = canary(
                self.repo,
                "deadbeef",
                logger,
                post=post,
                now=datetime(2026, 8, 1, 2, 0, tzinfo=timezone.utc),
            )
        self.assertEqual(result["status"], "PASS")
        self.assertIsNotNone(delivery)
        self.assertTrue(delivery.delivered)
        self.assertEqual(before, history_pair(self.repo)[1])
        self.assertIn("DQP operational canary", captured["text"])

    def test_canary_rejection_fails_without_mutation(self) -> None:
        self.write_history(different_bytes=True)
        before = history_pair(self.repo)[1]
        logger = logging.getLogger("canary-fail")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        with patch.dict(
            "os.environ",
            {"TELEGRAM_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "-100123"},
            clear=False,
        ):
            result, delivery = canary(
                self.repo,
                "deadbeef",
                logger,
                post=lambda *_args, **_kwargs: Response(
                    {"ok": False, "description": "blocked"}
                ),
            )
        self.assertEqual(result["status"], "FAIL")
        self.assertIsNotNone(delivery)
        self.assertFalse(delivery.delivered)
        self.assertEqual(before, history_pair(self.repo)[1])

    def test_canary_is_blocked_on_semantic_history_difference(self) -> None:
        self.write_history()
        (self.repo / "history.json.last-good").write_text("{}", encoding="utf-8")
        logger = logging.getLogger("canary-blocked")
        result, delivery = canary(self.repo, "deadbeef", logger)
        self.assertEqual(result["status"], "FAIL")
        self.assertIsNone(delivery)

    def test_atomic_json_and_overall_status(self) -> None:
        path = self.repo / "reports" / "gate.json"
        atomic_json(path, {"status": "PASS"})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "PASS")
        self.assertEqual(
            overall(
                [
                    {"status": "PASS", "critical": True},
                    {"status": "WARN", "critical": False},
                ]
            ),
            "PASS_WITH_WARNINGS",
        )
        self.assertEqual(
            overall([{"status": "FAIL", "critical": True}]),
            "FAIL",
        )

    def test_result_code_distinguishes_blocked_from_delivery_failure(self) -> None:
        blocked_checks = [
            {"name": "history_pair", "status": "FAIL", "critical": True},
            {"name": "telegram_canary", "status": "FAIL", "critical": True},
        ]
        self.assertEqual(result_code(blocked_checks, True, None), 30)
        delivery = TelegramDeliveryResult(
            kind="canary",
            subject="",
            required=True,
            attempted=True,
            delivered=False,
            outcome="api_rejected",
        )
        delivery_only = [
            {"name": "telegram_canary", "status": "FAIL", "critical": True}
        ]
        self.assertEqual(result_code(delivery_only, True, delivery), 23)
        self.assertEqual(canary_status(True, None), "BLOCKED")
        self.assertEqual(canary_status(True, delivery), "FAILED")


if __name__ == "__main__":
    unittest.main()
