#!/usr/bin/env python3
from __future__ import annotations

import ast
import unittest
from pathlib import Path

SCANNER = Path(__file__).resolve().parent.parent / "dividend_scanner.py"


class ScannerHistoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCANNER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_scanner_imports_history_store_contract(self) -> None:
        imported: set[str] = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module == "history_store":
                imported.update(alias.name for alias in node.names)
        self.assertEqual(
            imported,
            {"HistoryRecoveryRequired", "load_history", "save_history"},
        )

    def test_scanner_has_no_inline_history_load_or_save(self) -> None:
        function_names = {
            node.name
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("load_history", function_names)
        self.assertNotIn("save_history", function_names)

    def test_history_load_happens_before_market_universe_fetch(self) -> None:
        scan = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "scan"
        )
        calls: dict[str, list[ast.Call]] = {}
        for node in ast.walk(scan):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.setdefault(node.func.id, []).append(node)

        load_call = calls["load_history"][0]
        universe_call = calls["fetch_sp500_tickers"][0]
        self.assertLess(load_call.lineno, universe_call.lineno)
        self.assertTrue(
            any(keyword.arg == "logger" for keyword in load_call.keywords),
            "load_history must receive the production logger",
        )

    def test_history_save_uses_production_logger(self) -> None:
        save_calls = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "save_history"
        ]
        self.assertEqual(len(save_calls), 1)
        self.assertTrue(
            any(keyword.arg == "logger" for keyword in save_calls[0].keywords),
            "save_history must receive the production logger",
        )

    def test_history_recovery_exception_is_handled_explicitly(self) -> None:
        handlers = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name)
            and node.type.id == "HistoryRecoveryRequired"
        ]
        self.assertEqual(len(handlers), 1)
        self.assertIn("HISTORY_RECOVERY_REQUIRED", self.source)
        self.assertIn("Signals are blocked until history is recovered.", self.source)


if __name__ == "__main__":
    unittest.main()
