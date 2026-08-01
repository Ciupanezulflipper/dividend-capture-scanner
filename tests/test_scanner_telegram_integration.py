#!/usr/bin/env python3
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCANNER = ROOT / "dividend_scanner.py"


class ScannerTelegramIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCANNER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_scanner_imports_delivery_contract(self) -> None:
        self.assertIn("from telegram_delivery import send_telegram", self.source)

    def test_scanner_has_no_inline_send_telegram(self) -> None:
        names = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("send_telegram", names)

    def test_false_success_claims_are_removed(self) -> None:
        self.assertNotIn('logger.info("Daily heartbeat sent.")', self.source)
        self.assertNotIn('logger.info("Admin Telegram warning sent.")', self.source)

    def test_no_telegram_suppresses_admin_warning_and_heartbeat(self) -> None:
        self.assertIn("not args.no_telegram", self.source)
        self.assertIn('kind="admin_warning"', self.source)
        self.assertIn('kind="heartbeat"', self.source)

    def test_required_delivery_failure_exits_23(self) -> None:
        self.assertIn("required_delivery_failures", self.source)
        self.assertIn("raise SystemExit(23)", self.source)


if __name__ == "__main__":
    unittest.main()
