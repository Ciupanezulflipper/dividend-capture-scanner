#!/usr/bin/env python3
"""Crash-safe storage for Dividend Quality Pullback alert history.

The history is monotonic: alert keys are added and never intentionally removed.
Each save writes the same serialized snapshot to a backup and then the primary
file using same-directory temporary files, fsync, and os.replace.

On load, both copies are validated. The valid copy with more alert keys wins,
which recovers an interrupted primary replacement after the backup was already
committed. Corrupt copies are preserved under timestamped quarantine names.
If neither copy is usable, loading fails closed so old alerts cannot be silently
forgotten and resent.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

History = dict[str, Any]


class HistoryRecoveryRequired(RuntimeError):
    """Raised when no valid history snapshot remains."""


def backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.last-good")


def _log(logger: logging.Logger | None, level: int, message: str, *args: Any) -> None:
    if logger is not None:
        logger.log(level, message, *args)


def _read_snapshot(path: Path) -> History:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"history root must be a JSON object, got {type(payload).__name__}")
    return payload


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _quarantine(path: Path, logger: logging.Logger | None, reason: Exception) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    quarantined = path.with_name(
        f"{path.stem}.corrupt.{stamp}.{os.getpid()}{path.suffix}"
    )
    os.replace(path, quarantined)
    _fsync_directory(path.parent)
    _log(
        logger,
        logging.ERROR,
        "History snapshot quarantined | source=%s quarantine=%s error=%s",
        path,
        quarantined,
        reason,
    )
    return quarantined


def _validated_or_quarantined(
    path: Path,
    logger: logging.Logger | None,
) -> tuple[History | None, Path | None]:
    if not path.exists():
        return None, None
    try:
        return _read_snapshot(path), None
    except Exception as exc:
        return None, _quarantine(path, logger, exc)


def load_history(path: Path, logger: logging.Logger | None = None) -> History:
    """Load the newest usable monotonic history snapshot.

    The snapshot with more keys wins because alert history only grows. When the
    backup wins, the primary is atomically repaired before returning.
    """
    path = Path(path)
    backup = backup_path(path)
    primary_data, primary_quarantine = _validated_or_quarantined(path, logger)
    backup_data, backup_quarantine = _validated_or_quarantined(backup, logger)

    if primary_data is None and backup_data is None:
        if primary_quarantine is not None or backup_quarantine is not None:
            evidence = [
                str(item)
                for item in (primary_quarantine, backup_quarantine)
                if item is not None
            ]
            raise HistoryRecoveryRequired(
                "No valid history snapshot remains; recovery evidence: "
                + ", ".join(evidence)
            )
        return {}

    if primary_data is None:
        assert backup_data is not None
        _atomic_write_bytes(path, _serialize(backup_data))
        _log(
            logger,
            logging.WARNING,
            "History primary restored from backup | primary=%s backup=%s entries=%d",
            path,
            backup,
            len(backup_data),
        )
        return backup_data

    if backup_data is None:
        _atomic_write_bytes(backup, _serialize(primary_data))
        _log(
            logger,
            logging.WARNING,
            "History backup rebuilt from primary | primary=%s backup=%s entries=%d",
            path,
            backup,
            len(primary_data),
        )
        return primary_data

    if len(backup_data) > len(primary_data):
        _atomic_write_bytes(path, _serialize(backup_data))
        _log(
            logger,
            logging.WARNING,
            "History primary advanced from newer backup | primary_entries=%d backup_entries=%d",
            len(primary_data),
            len(backup_data),
        )
        return backup_data

    if len(primary_data) > len(backup_data):
        _atomic_write_bytes(backup, _serialize(primary_data))
        _log(
            logger,
            logging.WARNING,
            "History backup advanced from primary | primary_entries=%d backup_entries=%d",
            len(primary_data),
            len(backup_data),
        )

    return primary_data


def _serialize(history: History) -> bytes:
    if not isinstance(history, dict):
        raise TypeError("history must be a dictionary")
    text = json.dumps(
        history,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return (text + "\n").encode("utf-8")


def save_history(
    path: Path,
    history: History,
    logger: logging.Logger | None = None,
) -> None:
    """Persist one history snapshot to backup, then primary, atomically.

    Writing the backup first is safe because load_history chooses the valid
    snapshot with more keys. If primary replacement is interrupted, the next run
    promotes the newer backup instead of forgetting delivered alerts.
    """
    path = Path(path)
    backup = backup_path(path)
    payload = _serialize(history)
    _atomic_write_bytes(backup, payload)
    _atomic_write_bytes(path, payload)
    _log(
        logger,
        logging.INFO,
        "History snapshots committed | primary=%s backup=%s entries=%d",
        path,
        backup,
        len(history),
    )
