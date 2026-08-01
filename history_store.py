#!/usr/bin/env python3
"""Crash-safe storage for Dividend Quality Pullback alert history.

The alert history is monotonic: keys are added and never intentionally removed.
Each save writes the same serialized snapshot to a backup and then the primary
file using same-directory temporary files, fsync, and os.replace.

On load, both copies are validated. A strict superset wins, which recovers an
interrupted primary replacement after the backup was already committed. Corrupt
or conflicting snapshots are preserved under timestamped quarantine names. If
no trustworthy snapshot remains, a persistent recovery marker blocks subsequent
runs until a valid snapshot is restored.
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
    """Raised when no trustworthy history snapshot remains."""


def backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.last-good")


def recovery_marker_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.recovery-required")


def _log(logger: logging.Logger | None, level: int, message: str, *args: Any) -> None:
    if logger is not None:
        logger.log(level, message, *args)


def validate_history_snapshot(payload: Any) -> History:
    """Validate the persisted history shape without assuming optional fields."""
    if not isinstance(payload, dict):
        raise ValueError(
            f"history root must be a JSON object, got {type(payload).__name__}"
        )
    invalid_keys = [
        key for key, value in payload.items() if not isinstance(value, dict)
    ]
    if invalid_keys:
        preview = ", ".join(str(key) for key in invalid_keys[:3])
        raise ValueError(
            f"history entries must be JSON objects; invalid keys: {preview}"
        )
    return payload


def _read_snapshot(path: Path) -> History:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_history_snapshot(payload)


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


def _serialize_json_object(value: dict[str, Any]) -> bytes:
    text = json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return (text + "\n").encode("utf-8")


def _serialize(history: History) -> bytes:
    try:
        validated = validate_history_snapshot(history)
    except ValueError as exc:
        raise TypeError(str(exc)) from exc
    return _serialize_json_object(validated)


def _write_recovery_marker(
    path: Path,
    reason: str,
    evidence: list[Path],
) -> Path:
    marker = recovery_marker_path(path)
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "evidence": [str(item) for item in evidence],
    }
    _atomic_write_bytes(marker, _serialize_json_object(payload))
    return marker


def _clear_recovery_marker(path: Path, logger: logging.Logger | None) -> None:
    marker = recovery_marker_path(path)
    try:
        marker.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(marker.parent)
    _log(logger, logging.WARNING, "History recovery marker cleared | marker=%s", marker)


def _fail_closed(
    path: Path,
    reason: str,
    evidence: list[Path],
    logger: logging.Logger | None,
) -> None:
    marker = recovery_marker_path(path)
    if not marker.exists() or evidence:
        marker = _write_recovery_marker(path, reason, evidence)
    evidence_text = ", ".join(str(item) for item in evidence) or "preserved in marker"
    _log(
        logger,
        logging.CRITICAL,
        "History recovery required | marker=%s reason=%s evidence=%s",
        marker,
        reason,
        evidence_text,
    )
    raise HistoryRecoveryRequired(
        f"{reason}; marker={marker}; evidence={evidence_text}"
    )


def _quarantine_conflict_pair(
    path: Path,
    backup: Path,
    logger: logging.Logger | None,
    reason: str,
) -> list[Path]:
    return [
        _quarantine(path, logger, ValueError(reason)),
        _quarantine(backup, logger, ValueError(reason)),
    ]


def _common_entries_match(primary: History, backup: History) -> bool:
    common = primary.keys() & backup.keys()
    return all(primary[key] == backup[key] for key in common)


def load_history(path: Path, logger: logging.Logger | None = None) -> History:
    """Load and repair the newest trustworthy monotonic history snapshot."""
    path = Path(path)
    backup = backup_path(path)
    marker = recovery_marker_path(path)
    marker_preexisting = marker.exists()

    primary_data, primary_quarantine = _validated_or_quarantined(path, logger)
    backup_data, backup_quarantine = _validated_or_quarantined(backup, logger)
    quarantine_evidence = [
        item
        for item in (primary_quarantine, backup_quarantine)
        if item is not None
    ]

    if primary_data is None and backup_data is None:
        if marker_preexisting or quarantine_evidence:
            _fail_closed(
                path,
                "no valid history snapshot remains",
                quarantine_evidence,
                logger,
            )
        return {}

    if primary_data is None:
        assert backup_data is not None
        _atomic_write_bytes(path, _serialize(backup_data))
        _clear_recovery_marker(path, logger)
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
        _clear_recovery_marker(path, logger)
        _log(
            logger,
            logging.WARNING,
            "History backup rebuilt from primary | primary=%s backup=%s entries=%d",
            path,
            backup,
            len(primary_data),
        )
        return primary_data

    if not _common_entries_match(primary_data, backup_data):
        evidence = _quarantine_conflict_pair(
            path,
            backup,
            logger,
            "history snapshots disagree on existing alert entries",
        )
        _fail_closed(
            path,
            "history snapshots disagree on existing alert entries",
            evidence,
            logger,
        )

    if len(backup_data) > len(primary_data):
        _atomic_write_bytes(path, _serialize(backup_data))
        _clear_recovery_marker(path, logger)
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
        _clear_recovery_marker(path, logger)
        _log(
            logger,
            logging.WARNING,
            "History backup advanced from primary | primary_entries=%d backup_entries=%d",
            len(primary_data),
            len(backup_data),
        )
        return primary_data

    if primary_data != backup_data:
        evidence = _quarantine_conflict_pair(
            path,
            backup,
            logger,
            "history snapshots have equal size but different keys",
        )
        _fail_closed(
            path,
            "history snapshots have equal size but different keys",
            evidence,
            logger,
        )

    _clear_recovery_marker(path, logger)
    return primary_data


def restore_history(
    path: Path,
    history: History,
    logger: logging.Logger | None = None,
) -> None:
    """Explicitly restore a validated snapshot and clear a recovery block.

    This operation is intentionally separate from save_history so normal scanner
    execution can never bypass a recovery marker.
    """
    path = Path(path)
    backup = backup_path(path)
    payload = _serialize(history)
    _atomic_write_bytes(backup, payload)
    _atomic_write_bytes(path, payload)
    _clear_recovery_marker(path, logger)
    _log(
        logger,
        logging.WARNING,
        "History explicitly restored | primary=%s backup=%s entries=%d",
        path,
        backup,
        len(history),
    )


def save_history(
    path: Path,
    history: History,
    logger: logging.Logger | None = None,
) -> None:
    """Persist one history snapshot to backup, then primary, atomically.

    Writing the backup first is safe because load_history chooses a strict
    superset. If primary replacement is interrupted, the next run promotes the
    newer backup instead of forgetting delivered alerts.
    """
    path = Path(path)
    marker = recovery_marker_path(path)
    if marker.exists():
        raise HistoryRecoveryRequired(
            f"history save blocked by recovery marker: {marker}"
        )

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
