#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from history_store import backup_path, recovery_marker_path
from tools.history_recovery import command_restore, command_status


class HistoryRecoveryToolTests(unittest.TestCase):
    def test_status_reports_snapshot_and_marker_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "history.json"
            history_file.write_text(
                json.dumps({"a": {"symbol": "AEP"}}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(command_status(history_file), 0)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["history"]["valid"])
            self.assertEqual(payload["history"]["entries"], 1)
            self.assertFalse(payload["backup"]["exists"])
            self.assertFalse(payload["recovery_marker"]["exists"])

    def test_restore_requires_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "history.json"
            source = Path(tmp) / "candidate.json"
            source.write_text(json.dumps({"a": {}}), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "--force is required"):
                command_restore(history_file, source, force=False)
            self.assertFalse(history_file.exists())

    def test_restore_rejects_non_history_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "history.json"
            source = Path(tmp) / "marker.json"
            source.write_text(
                json.dumps({"reason": "not history"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "entries must be JSON objects"):
                command_restore(history_file, source, force=True)
            self.assertFalse(history_file.exists())

    def test_restore_rebuilds_both_copies_and_clears_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_file = Path(tmp) / "history.json"
            source = Path(tmp) / "candidate.json"
            candidate = {
                "a": {"symbol": "AEP"},
                "b": {"symbol": "UDR"},
            }
            source.write_text(json.dumps(candidate), encoding="utf-8")
            recovery_marker_path(history_file).write_text(
                "blocked",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    command_restore(history_file, source, force=True),
                    0,
                )
            self.assertIn("RESTORE_STATUS=PASSED entries=2", output.getvalue())
            self.assertEqual(json.loads(history_file.read_text()), candidate)
            self.assertEqual(
                json.loads(backup_path(history_file).read_text()),
                candidate,
            )
            self.assertFalse(recovery_marker_path(history_file).exists())


if __name__ == "__main__":
    unittest.main()
