#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import history_store
from history_store import (
    HistoryRecoveryRequired,
    backup_path,
    load_history,
    recovery_marker_path,
    save_history,
)


class HistoryStoreTests(unittest.TestCase):
    def test_missing_history_returns_empty_without_creating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            self.assertEqual(load_history(path), {})
            self.assertFalse(path.exists())
            self.assertFalse(backup_path(path).exists())
            self.assertFalse(recovery_marker_path(path).exists())

    def test_save_writes_matching_primary_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            history = {"a": {"symbol": "AEP"}}
            save_history(path, history)
            self.assertEqual(load_history(path), history)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                json.loads(backup_path(path).read_text(encoding="utf-8")),
            )

    def test_corrupt_primary_is_quarantined_and_restored_from_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            history = {"a": {"symbol": "AEP"}}
            save_history(path, history)
            path.write_text("{broken", encoding="utf-8")

            self.assertEqual(load_history(path), history)
            quarantined = list(Path(tmp).glob("history.corrupt.*.json"))
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_text(encoding="utf-8"), "{broken")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), history)

    def test_corrupt_backup_is_quarantined_and_rebuilt_from_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            history = {"a": {"symbol": "AEP"}}
            save_history(path, history)
            backup_path(path).write_text("[]", encoding="utf-8")

            self.assertEqual(load_history(path), history)
            quarantined = list(Path(tmp).glob("history.json.corrupt.*.last-good"))
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0].read_text(encoding="utf-8"), "[]")
            self.assertEqual(json.loads(backup_path(path).read_text()), history)

    def test_both_corrupt_fails_closed_persistently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text("{bad-primary", encoding="utf-8")
            backup_path(path).write_text("{bad-backup", encoding="utf-8")

            with self.assertRaises(HistoryRecoveryRequired):
                load_history(path)

            evidence = list(Path(tmp).glob("*.corrupt.*"))
            self.assertEqual(len(evidence), 2)
            marker = recovery_marker_path(path)
            self.assertTrue(marker.exists())
            self.assertFalse(path.exists())
            self.assertFalse(backup_path(path).exists())

            with self.assertRaises(HistoryRecoveryRequired):
                load_history(path)
            self.assertTrue(marker.exists())

    def test_restored_valid_primary_clears_recovery_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            recovery_marker_path(path).write_text("blocked", encoding="utf-8")
            restored = {"a": {"symbol": "AEP"}}
            path.write_text(json.dumps(restored), encoding="utf-8")

            self.assertEqual(load_history(path), restored)
            self.assertFalse(recovery_marker_path(path).exists())
            self.assertEqual(json.loads(backup_path(path).read_text()), restored)

    def test_save_is_blocked_while_recovery_marker_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            recovery_marker_path(path).write_text("blocked", encoding="utf-8")
            with self.assertRaises(HistoryRecoveryRequired):
                save_history(path, {"a": {}})
            self.assertFalse(path.exists())
            self.assertFalse(backup_path(path).exists())

    def test_newer_backup_recovers_interrupted_primary_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            old = {"a": {"symbol": "AEP"}}
            new = {**old, "b": {"symbol": "UDR"}}
            save_history(path, old)

            real_replace = os.replace

            def fail_primary_replace(
                source: str | os.PathLike[str],
                target: str | os.PathLike[str],
            ) -> None:
                if Path(target) == path:
                    raise OSError("simulated primary replace interruption")
                real_replace(source, target)

            with mock.patch.object(
                history_store.os,
                "replace",
                side_effect=fail_primary_replace,
            ):
                with self.assertRaises(OSError):
                    save_history(path, new)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), old)
            self.assertEqual(
                json.loads(backup_path(path).read_text(encoding="utf-8")),
                new,
            )
            self.assertEqual(load_history(path), new)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), new)
            self.assertEqual(list(Path(tmp).glob(".*.tmp")), [])

    def test_primary_with_more_entries_repairs_stale_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            primary = {"a": {}, "b": {}}
            backup = {"a": {}}
            path.write_text(json.dumps(primary), encoding="utf-8")
            backup_path(path).write_text(json.dumps(backup), encoding="utf-8")

            self.assertEqual(load_history(path), primary)
            self.assertEqual(json.loads(backup_path(path).read_text()), primary)

    def test_conflicting_existing_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text(json.dumps({"a": {"symbol": "AEP"}}), encoding="utf-8")
            backup_path(path).write_text(
                json.dumps({"a": {"symbol": "UDR"}, "b": {}}),
                encoding="utf-8",
            )

            with self.assertRaises(HistoryRecoveryRequired):
                load_history(path)
            self.assertTrue(recovery_marker_path(path).exists())
            self.assertEqual(len(list(Path(tmp).glob("*.corrupt.*"))), 2)

    def test_equal_size_different_keys_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text(json.dumps({"a": {}}), encoding="utf-8")
            backup_path(path).write_text(json.dumps({"b": {}}), encoding="utf-8")

            with self.assertRaises(HistoryRecoveryRequired):
                load_history(path)
            self.assertTrue(recovery_marker_path(path).exists())

    def test_non_dictionary_root_is_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(HistoryRecoveryRequired):
                load_history(path)
            self.assertTrue(recovery_marker_path(path).exists())
            self.assertEqual(
                len(list(Path(tmp).glob("history.corrupt.*.json"))),
                1,
            )


if __name__ == "__main__":
    unittest.main()
