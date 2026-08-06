#!/usr/bin/env python3
"""Run the audit-enhanced scanner through guarded production reliability.

This entry point preserves the existing production runner and adds two narrow
operational capabilities around it:

- a bounded Yahoo/Telegram network preflight before live scans;
- an optional external runtime status event after every attempted run.

Dry runs remain unchanged and do not wait on the preflight.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from telegram_delivery import TelegramDeliveryResult, send_telegram  # noqa: E402
from tools import run_production_scan as production  # noqa: E402
from tools.network_preflight import PreflightResult, ProbeResult, run_preflight  # noqa: E402
from tools.runtime_monitor import MonitorPublishResult, publish_runtime_event  # noqa: E402

production.SCANNER_SCRIPT = REPO_ROOT / "quality_scanner.py"

OUTAGE_STATE_FILE = REPO_ROOT / ".runtime" / "network_outage.json"


def _env_value(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is not None:
        return value
    return production._read_dotenv_values(REPO_ROOT / ".env", (key,)).get(
        key, default
    )


def _env_int(key: str, default: int, minimum: int = 0) -> int:
    raw = _env_value(key, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _enabled(key: str, default: bool = True) -> bool:
    raw = _env_value(key, "1" if default else "0").strip().casefold()
    return raw not in {"0", "false", "no", "off"}


def network_preflight_required(args: Sequence[str]) -> bool:
    return (
        _enabled("DQP_NETWORK_PREFLIGHT_ENABLED", True)
        and "--dry-run" not in args
    )


def _preflight_progress(
    attempt: int, maximum: int, results: Sequence[ProbeResult]
) -> None:
    summary = " ".join(
        f"{item.name}={'PASS' if item.ok else 'FAIL'}"
        for item in results
    )
    print(f"[network-preflight] attempt {attempt}/{maximum}: {summary}")
    if attempt < maximum and any(item.critical and not item.ok for item in results):
        interval = _env_int("DQP_PREFLIGHT_INTERVAL_SECONDS", 300, 0)
        print(f"[network-preflight] retrying in {interval} seconds")


def execute_preflight(args: Sequence[str]) -> PreflightResult | None:
    if not network_preflight_required(args):
        return None
    token = _env_value("TELEGRAM_TOKEN")
    require_telegram = "--no-telegram" not in args
    return run_preflight(
        token,
        require_telegram=require_telegram,
        max_wait_seconds=_env_int("DQP_PREFLIGHT_MAX_WAIT_SECONDS", 1_800, 0),
        interval_seconds=_env_int("DQP_PREFLIGHT_INTERVAL_SECONDS", 300, 0),
        timeout_seconds=_env_int("DQP_PREFLIGHT_TIMEOUT_SECONDS", 15, 1),
        on_attempt=_preflight_progress,
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_outage_state() -> dict[str, Any] | None:
    return _load_json(OUTAGE_STATE_FILE)


def _write_outage_state(preflight: PreflightResult, now: datetime) -> None:
    previous = _load_outage_state() or {}
    production.atomic_write_json(
        OUTAGE_STATE_FILE,
        {
            "schema_version": 1,
            "first_failure_utc": previous.get("first_failure_utc") or now.isoformat(),
            "last_failure_utc": now.isoformat(),
            "attempts": preflight.attempts,
            "waited_seconds": preflight.waited_seconds,
            "results": [asdict(item) for item in preflight.results],
        },
    )


def _recovery_logger() -> logging.Logger:
    logger = logging.getLogger("dqp_network_recovery")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    path = production.resolve_log_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
    logger.addHandler(handler)
    return logger


def send_recovery_notice(
    outage: dict[str, Any] | None,
) -> TelegramDeliveryResult | None:
    if not outage:
        return None
    token = _env_value("TELEGRAM_TOKEN")
    chat_id = _env_value("TELEGRAM_CHAT_ID")
    first_failure = str(outage.get("first_failure_utc") or "unknown")
    result = send_telegram(
        token,
        chat_id,
        "DQP NETWORK RECOVERED\n"
        f"Previous outage detected: {first_failure}\n"
        "Yahoo and Telegram preflight passed. Scanner is starting now.",
        _recovery_logger(),
        kind="network_recovery",
        subject=first_failure,
        required=False,
    )
    print(
        "[network-preflight] recovery notice: "
        + ("DELIVERED" if result.delivered else result.outcome.upper())
    )
    if result.delivered:
        OUTAGE_STATE_FILE.unlink(missing_ok=True)
    return result


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _monitor_topic() -> str:
    return _env_value("DQP_MONITOR_TOPIC")


def _publish(
    event: str,
    *,
    scan_date: str,
    success: bool,
    finished_at_utc: str,
    failure_reasons: Sequence[str],
    duration_seconds: float,
) -> MonitorPublishResult:
    return publish_runtime_event(
        _monitor_topic(),
        event,
        {
            "scan_date": scan_date,
            "success": success,
            "finished_at_utc": finished_at_utc,
            "failure_reasons": list(failure_reasons),
            "duration_seconds": duration_seconds,
            "git_head": _git_head(),
        },
        timeout_seconds=_env_int("DQP_MONITOR_TIMEOUT_SECONDS", 15, 1),
    )


def _current_scan_date() -> str:
    return datetime.now(production.NEW_YORK).date().isoformat()


def write_preflight_failure(
    args: Sequence[str], preflight: PreflightResult, started_at: datetime
) -> int:
    finished_at = datetime.now(timezone.utc)
    scan_date = _current_scan_date()
    report_dir = production.resolve_report_dir(args)
    run_health_path = report_dir / f"run_health_{scan_date}.json"
    _write_outage_state(preflight, finished_at)

    monitor = _publish(
        "network_preflight_failed",
        scan_date=scan_date,
        success=False,
        finished_at_utc=finished_at.isoformat(),
        failure_reasons=("network_preflight_failed",),
        duration_seconds=round((finished_at - started_at).total_seconds(), 3),
    )
    warnings: list[str] = []
    if monitor.configured and not monitor.delivered:
        warnings.append("runtime_monitor_publish_failed")

    payload: dict[str, Any] = {
        "schema_version": 2,
        "scan_date": scan_date,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "scanner_exit_code": None,
        "scanner_timed_out": False,
        "run_skipped_weekend": False,
        "scanner_health_path": None,
        "scanner_health_fresh": False,
        "scan_report_path": None,
        "scan_report_fresh": False,
        "report_expected": "--report" in args and "--no-report" not in args,
        "report_audit": None,
        "telegram_audit": None,
        "network_preflight": asdict(preflight),
        "network_recovery_delivery": None,
        "runtime_monitor": asdict(monitor),
        "warnings": warnings,
        "failure_reasons": ["network_preflight_failed"],
        "success": False,
    }
    production.atomic_write_json(run_health_path, payload)
    print(
        "[production-runner] FAIL: network preflight exhausted before scanner start",
        file=sys.stderr,
    )
    print(f"[production-runner] Health artifact: {run_health_path}")
    return 25


def enrich_run_health(
    args: Sequence[str],
    preflight: PreflightResult | None,
    recovery: TelegramDeliveryResult | None,
    exit_code: int,
) -> None:
    scan_date = _current_scan_date()
    report_dir = production.resolve_report_dir(args)
    path = report_dir / f"run_health_{scan_date}.json"
    payload = _load_json(path)
    if payload is None:
        # The base runner already treats a missing health artifact as a failure.
        _publish(
            "run_failure",
            scan_date=scan_date,
            success=False,
            finished_at_utc=datetime.now(timezone.utc).isoformat(),
            failure_reasons=("run_health_missing", f"exit_code={exit_code}"),
            duration_seconds=0.0,
        )
        return

    success = bool(payload.get("success")) and exit_code == 0
    failure_reasons = [str(item) for item in payload.get("failure_reasons") or []]
    finished = str(payload.get("finished_at_utc") or datetime.now(timezone.utc).isoformat())
    duration = float(payload.get("duration_seconds") or 0.0)
    monitor = _publish(
        "run_success" if success else "run_failure",
        scan_date=scan_date,
        success=success,
        finished_at_utc=finished,
        failure_reasons=failure_reasons,
        duration_seconds=duration,
    )

    warnings = [str(item) for item in payload.get("warnings") or []]
    if monitor.configured and not monitor.delivered:
        warnings.append("runtime_monitor_publish_failed")
    payload["schema_version"] = max(int(payload.get("schema_version") or 1), 2)
    payload["network_preflight"] = asdict(preflight) if preflight else None
    payload["network_recovery_delivery"] = asdict(recovery) if recovery else None
    payload["runtime_monitor"] = asdict(monitor)
    payload["warnings"] = sorted(set(warnings))
    production.atomic_write_json(path, payload)
    if monitor.configured:
        print(
            "[runtime-monitor] "
            + ("PUBLISHED" if monitor.delivered else f"WARN:{monitor.outcome}")
        )


def run(args: Sequence[str]) -> int:
    started_at = datetime.now(timezone.utc)
    preflight = execute_preflight(args)
    if preflight is not None and not preflight.passed:
        return write_preflight_failure(args, preflight, started_at)

    recovery = send_recovery_notice(_load_outage_state()) if preflight else None
    exit_code = production.run(args)
    enrich_run_health(args, preflight, recovery, exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
