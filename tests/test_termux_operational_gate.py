#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.termux_gate_core import (
    atomic_json,
    cron_audit,
    history_pair,
    parse_crontab,
    redact,
)
from tools.termux_gate_runtime import boot_audit, timezone_audit
from tools.termux_operational_gate import canary, overall


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

    def write_history(self) -> None:
        payload = {
            "AAPL:2026-08-07": {"symbol": "AAPL"},
            "MSFT:2026-08-14": {"symbol": "MSFT"},
        }
        text = json.dumps(payload, sort_keys=True)
        (self.repo / "history.json").write_text(text, encoding="utf-8")
        (self.repo / "history.json.last-good").write_text(text, encoding="utf-8")

    def test_redact_hides_assignment_and_bot_url(self) -> None:
        output = redact("TELEGRAM_TOKEN=secret /botother-secret/sendMessage")
        self.assertNotIn("secret", output)
        self.assertIn("[REDACTED]", output)

    def test_parse_crontab_keeps_zone_and_entry(self) -> None:
        variables, entries = parse_crontab(
            "CRON_TZ=America/New_York\n"
            "0 10 * * 1-5 cd /tmp/app && ./run_bot.sh --daily-heartbeat\n"
        )
        self.assertEqual(variables["CRON_TZ"], "America/New_York")
        self.assertEqual(entries[0][0], "0 10 * * 1-5")

    def test_cron_audit_matches_path_schedule_and_args(self) -> None:
        text = (
            "CRON_TZ=America/New_York\n"
            f"0 10 * * 1-5 {self.repo}/run_bot.sh --daily-heartbeat --report\n"
        )
        result, variables = cron_audit(
            self.repo,
            "0 10 * * 1-5",
            ["--daily-heartbeat", "--report"],
            lambda _: (0, text, ""),
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(variables["CRON_TZ"], "America/New_York")

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
            "America/New_York",
            {"CRON_TZ": "America/New_York"},
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

    def test_history_pair_requires_equal_valid_files(self) -> None:
        self.write_history()
        result, hashes = history_pair(self.repo)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(hashes["primary"], hashes["backup"])
        (self.repo / "history.json.last-good").write_text("{}", encoding="utf-8")
        self.assertEqual(history_pair(self.repo)[0]["status"], "FAIL")

    def test_canary_success_keeps_history_unchanged(self) -> None:
        self.write_history()
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
        self.assertTrue(delivery.delivered)
        self.assertEqual(before, history_pair(self.repo)[1])
        self.assertIn("DQP operational canary", captured["text"])

    def test_canary_rejection_fails_without_mutation(self) -> None:
        self.write_history()
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
                post=lambda *_args, **_kwargs: Response({"ok": False, "description": "blocked"}),
            )
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(delivery.delivered)
        self.assertEqual(before, history_pair(self.repo)[1])

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


if __name__ == "__main__":
    unittest.main()
