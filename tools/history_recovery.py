#!/usr/bin/env python3
"""Inspect or explicitly restore Dividend Quality Pullback alert history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from history_store import (
    backup_path,
    load_history,
    recovery_marker_path,
    restore_history,
    validate_history_snapshot,
)


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        return validate_history_snapshot(payload)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def snapshot_status(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return result
    try:
        payload = read_json_object(path)
        result.update({"valid": True, "entries": len(payload)})
    except Exception as exc:
        result.update({"valid": False, "error": str(exc)})
    return result


def command_status(history_file: Path) -> int:
    marker = recovery_marker_path(history_file)
    quarantines = sorted(
        str(path)
        for path in history_file.parent.glob(f"{history_file.stem}.corrupt.*")
    )
    backup_quarantines = sorted(
        str(path)
        for path in history_file.parent.glob(f"{history_file.name}.corrupt.*")
    )
    payload = {
        "history": snapshot_status(history_file),
        "backup": snapshot_status(backup_path(history_file)),
        "recovery_marker": {
            "path": str(marker),
            "exists": marker.exists(),
        },
        "quarantine_files": sorted(set(quarantines + backup_quarantines)),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_restore(history_file: Path, source_file: Path, force: bool) -> int:
    if not force:
        raise SystemExit("RESTORE_STATUS=BLOCKED --force is required")
    history = read_json_object(source_file)
    restore_history(history_file, history)
    verified = load_history(history_file)
    if verified != history:
        raise SystemExit("RESTORE_STATUS=FAILED verification mismatch")
    print(f"RESTORE_STATUS=PASSED entries={len(history)} source={source_file}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history-file",
        type=Path,
        default=Path("history.json"),
        help="Primary history file (default: history.json)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "status",
        help="Inspect primary, backup, marker, and quarantines",
    )
    restore = subparsers.add_parser(
        "restore",
        help="Restore from a validated alert-history JSON snapshot",
    )
    restore.add_argument("--from-file", type=Path, required=True)
    restore.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    history_file = args.history_file.expanduser().resolve()
    if args.command == "status":
        raise SystemExit(command_status(history_file))
    source_file = args.from_file.expanduser().resolve()
    raise SystemExit(command_restore(history_file, source_file, args.force))


if __name__ == "__main__":
    main()
