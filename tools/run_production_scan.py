#!/usr/bin/env python3
"""Production reliability wrapper for the Dividend Quality Pullback scanner.

The existing scanner owns market-data and signal logic. This wrapper adds
operational truth around one execution without changing strategy:

- runs ``dividend_scanner.py`` with the original CLI arguments;
- requires fresh health/report artifacts from this execution;
- detects DNS/TLS/provider collapse using production error patterns;
- verifies Telegram success from newly appended scanner log records;
- writes an atomic ``run_health_YYYY-MM-DD.json`` artifact;
- returns non-zero when a production run is not operationally healthy.

No credentials are printed or written to the health artifact.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNER_SCRIPT = REPO_ROOT / "dividend_scanner.py"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"
DEFAULT_LOG_FILE = REPO_ROOT / "stock_scan.log"
NEW_YORK = ZoneInfo("America/New_York")
DEFAULT_SCAN_TIMEOUT_SECONDS = 7_200

PROVIDER_ERROR_MARKERS = (
    "no address associated with hostname",
    "name resolution error",
    "nameresolutionerror",
    "temporary failure in name resolution",
    "failed to resolve",
    "hostname mismatch",
    "certificate verify failed",
    "sslerror",
    "ssl:",
    "curl error",
    "failed to perform",
    "max retries exceeded",
    "connection reset",
    "connection aborted",
    "connection refused",
    "network is unreachable",
    "connect timeout",
    "read timeout",
    "timed out",
)

TELEGRAM_FAILURE_MARKERS = (
    "Telegram send failed:",
    "Telegram API error ",
)


@dataclass(frozen=True)
class ReportAudit:
    report_present: bool
    total_rows: int
    usable_ex_date: int
    price_count: int
    provider_errors: int
    provider_failure_rate: float
    yfinance_error_rows: int
    is_collapsed: bool
    is_degraded: bool


@dataclass(frozen=True)
class TelegramAudit:
    credentials_present: bool
    delivery_required: bool
    heartbeat_required: bool
    heartbeat_claimed: bool
    admin_warning_claimed: bool
    signal_attempt_count: int
    signal_success_count: int
    signal_failure_count: int
    failure_line_count: int
    delivery_verified: bool


Fingerprint = tuple[int, int]


def _arg_present(args: Sequence[str], flag: str) -> bool:
    return flag in args


def _arg_value(args: Sequence[str], flag: str) -> str | None:
    prefix = f"{flag}="
    for index, arg in enumerate(args):
        if arg.startswith(prefix):
            return arg[len(prefix) :]
        if arg == flag and index + 1 < len(args):
            return args[index + 1]
    return None


def resolve_report_dir(args: Sequence[str]) -> Path:
    configured = _arg_value(args, "--report-dir")
    if configured is None:
        configured = os.getenv("REPORT_DIR")
    if not configured:
        return DEFAULT_REPORT_DIR
    path = Path(configured).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _read_dotenv_presence(path: Path, keys: Iterable[str]) -> dict[str, bool]:
    values = _read_dotenv_values(path, keys)
    return {key: bool(values.get(key)) for key in keys}


def _read_dotenv_values(path: Path, keys: Iterable[str]) -> dict[str, str]:
    wanted = set(keys)
    found: dict[str, str] = {}
    if not path.exists():
        return found
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key not in wanted:
                continue
            found[key] = value.strip().strip('"').strip("'")
    except OSError:
        return found
    return found


def telegram_credentials_present() -> bool:
    if bool(os.getenv("TELEGRAM_TOKEN")) and bool(os.getenv("TELEGRAM_CHAT_ID")):
        return True
    dotenv = _read_dotenv_presence(
        REPO_ROOT / ".env", ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")
    )
    return dotenv["TELEGRAM_TOKEN"] and dotenv["TELEGRAM_CHAT_ID"]


def resolve_log_file() -> Path:
    configured = os.getenv("LOG_FILE")
    if not configured:
        configured = _read_dotenv_values(REPO_ROOT / ".env", ("LOG_FILE",)).get(
            "LOG_FILE"
        )
    if not configured:
        return DEFAULT_LOG_FILE
    path = Path(configured).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def log_offset(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def read_log_delta(path: Path, offset: int) -> str:
    try:
        current_size = path.stat().st_size
        safe_offset = offset if current_size >= offset else 0
        with path.open("rb") as handle:
            handle.seek(safe_offset)
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def file_fingerprint(path: Path) -> Fingerprint | None:
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def snapshot_artifacts(directory: Path, pattern: str) -> dict[Path, Fingerprint]:
    if not directory.exists():
        return {}
    snapshot: dict[Path, Fingerprint] = {}
    for path in directory.glob(pattern):
        fingerprint = file_fingerprint(path)
        if fingerprint is not None:
            snapshot[path] = fingerprint
    return snapshot


def discover_fresh_artifact(
    directory: Path,
    pattern: str,
    before: dict[Path, Fingerprint],
) -> Path | None:
    if not directory.exists():
        return None
    fresh: list[tuple[int, Path]] = []
    for path in directory.glob(pattern):
        fingerprint = file_fingerprint(path)
        if fingerprint is None or before.get(path) == fingerprint:
            continue
        fresh.append((fingerprint[0], path))
    return max(fresh, default=(0, None), key=lambda item: item[0])[1]


def contains_provider_error(value: Any) -> bool:
    text = str(value or "").casefold()
    return any(marker in text for marker in PROVIDER_ERROR_MARKERS)


def _nonempty(row: dict[str, str], *keys: str) -> bool:
    return any(
        str(row.get(key, "")).strip().casefold() not in ("", "none", "nan")
        for key in keys
    )


def audit_report(path: Path, degraded_rate: float = 0.20) -> ReportAudit:
    if not path.exists():
        return ReportAudit(False, 0, 0, 0, 0, 1.0, 0, True, True)

    total = 0
    usable_ex_date = 0
    price_count = 0
    provider_errors = 0
    yfinance_error_rows = 0

    try:
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                total += 1
                if _nonempty(row, "chosen_ex_date", "ex_date"):
                    usable_ex_date += 1
                if _nonempty(row, "price"):
                    price_count += 1
                combined = " | ".join(
                    str(row.get(key, ""))
                    for key in ("yf_ex_date_error", "error", "skip_reason")
                )
                if contains_provider_error(combined):
                    provider_errors += 1
                if str(row.get("reason_category", "")).strip() == "yfinance_error":
                    yfinance_error_rows += 1
    except (OSError, csv.Error, UnicodeError):
        return ReportAudit(True, 0, 0, 0, 0, 1.0, 0, True, True)

    rate = provider_errors / total if total else 1.0
    collapsed = (
        total == 0
        or usable_ex_date == 0
        or price_count == 0
        or rate >= 0.80
    )
    degraded = collapsed or rate >= degraded_rate
    return ReportAudit(
        True,
        total,
        usable_ex_date,
        price_count,
        provider_errors,
        round(rate, 4),
        yfinance_error_rows,
        collapsed,
        degraded,
    )


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


def audit_telegram(
    log_delta: str,
    args: Sequence[str],
    scanner_collapsed: bool,
    credentials_present: bool,
    run_skipped: bool = False,
) -> TelegramAudit:
    dry_run = _arg_present(args, "--dry-run")
    no_telegram = _arg_present(args, "--no-telegram")
    heartbeat_requested = _arg_present(args, "--daily-heartbeat")

    lines = log_delta.splitlines()
    explicit_failures = [
        line for line in lines if any(marker in line for marker in TELEGRAM_FAILURE_MARKERS)
    ]
    signal_attempt_count = sum(1 for line in lines if "Telegram alert for " in line)
    signal_failure_count = sum(
        1 for line in lines if re.search(r"Telegram alert for .+: FAILED\s*$", line)
    )
    signal_success_count = sum(
        1 for line in lines if re.search(r"Telegram alert for .+: sent\s*$", line)
    )
    heartbeat_claimed = any("Daily heartbeat sent." in line for line in lines)
    admin_warning_claimed = any("Admin Telegram warning sent." in line for line in lines)

    live_telegram_allowed = not dry_run and not no_telegram and not run_skipped
    delivery_required = live_telegram_allowed and (
        heartbeat_requested or scanner_collapsed or signal_attempt_count > 0
    )
    heartbeat_required = delivery_required and heartbeat_requested and not scanner_collapsed

    delivery_verified = True
    if delivery_required and not credentials_present:
        delivery_verified = False
    if explicit_failures or signal_failure_count:
        delivery_verified = False
    if heartbeat_required and not heartbeat_claimed:
        delivery_verified = False
    if scanner_collapsed and delivery_required and credentials_present:
        if not admin_warning_claimed:
            delivery_verified = False

    return TelegramAudit(
        credentials_present=credentials_present,
        delivery_required=delivery_required,
        heartbeat_required=heartbeat_required,
        heartbeat_claimed=heartbeat_claimed,
        admin_warning_claimed=admin_warning_claimed,
        signal_attempt_count=signal_attempt_count,
        signal_success_count=signal_success_count,
        signal_failure_count=signal_failure_count,
        failure_line_count=len(explicit_failures),
        delivery_verified=delivery_verified,
    )


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _status_exit_code(failure_reasons: Sequence[str]) -> int:
    if not failure_reasons:
        return 0
    if any(reason.startswith("scanner_exit_code=") for reason in failure_reasons):
        return 20
    if any("health" in reason or "report" in reason for reason in failure_reasons):
        return 21
    if any("provider" in reason or "collapsed" in reason for reason in failure_reasons):
        return 22
    if any("telegram" in reason for reason in failure_reasons):
        return 23
    return 24


def _scan_timeout_seconds() -> int:
    raw = os.getenv("DQP_SCAN_TIMEOUT_SECONDS", str(DEFAULT_SCAN_TIMEOUT_SECONDS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_SCAN_TIMEOUT_SECONDS
    return value if value >= 60 else DEFAULT_SCAN_TIMEOUT_SECONDS


def _date_from_health_path(path: Path | None) -> str:
    if path is not None:
        match = re.fullmatch(r"scan_health_(\d{4}-\d{2}-\d{2})\.json", path.name)
        if match:
            return match.group(1)
    return datetime.now(NEW_YORK).date().isoformat()


def run(scanner_args: Sequence[str]) -> int:
    if not SCANNER_SCRIPT.exists():
        print(f"[production-runner] FAIL: missing {SCANNER_SCRIPT}", file=sys.stderr)
        return 20

    report_dir = resolve_report_dir(scanner_args)
    health_before = snapshot_artifacts(report_dir, "scan_health_*.json")
    report_before = snapshot_artifacts(report_dir, "scan_report_*.csv")

    log_file = resolve_log_file()
    before_offset = log_offset(log_file)
    started_at = datetime.now(timezone.utc)
    timed_out = False

    try:
        completed = subprocess.run(
            [sys.executable, str(SCANNER_SCRIPT), *scanner_args],
            cwd=REPO_ROOT,
            check=False,
            timeout=_scan_timeout_seconds(),
        )
        scanner_exit_code = completed.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        scanner_exit_code = 124
        print("[production-runner] Scanner exceeded execution timeout.", file=sys.stderr)

    finished_at = datetime.now(timezone.utc)
    log_delta = read_log_delta(log_file, before_offset)

    health_path = discover_fresh_artifact(
        report_dir, "scan_health_*.json", health_before
    )
    report_path = discover_fresh_artifact(
        report_dir, "scan_report_*.csv", report_before
    )
    scan_date = _date_from_health_path(health_path)
    expected_report_path = report_dir / f"scan_report_{scan_date}.csv"
    run_health_path = report_dir / f"run_health_{scan_date}.json"

    scanner_health = _load_json(health_path)
    scanner_collapsed = bool(scanner_health and scanner_health.get("is_collapsed"))

    now_ny = datetime.now(NEW_YORK)
    run_skipped_weekend = (
        now_ny.weekday() >= 5
        and not _arg_present(scanner_args, "--force-weekend")
        and scanner_exit_code == 0
        and health_path is None
    )

    report_expected = (
        _arg_present(scanner_args, "--report")
        and not _arg_present(scanner_args, "--no-report")
        and not run_skipped_weekend
    )
    if report_expected and report_path != expected_report_path:
        report_path = None
    report_audit = audit_report(report_path) if report_path is not None else ReportAudit(
        False,
        0,
        0,
        0,
        0,
        1.0 if report_expected else 0.0,
        0,
        report_expected,
        report_expected,
    )

    telegram_audit = audit_telegram(
        log_delta=log_delta,
        args=scanner_args,
        scanner_collapsed=scanner_collapsed,
        credentials_present=telegram_credentials_present(),
        run_skipped=run_skipped_weekend,
    )

    failure_reasons: list[str] = []
    warnings: list[str] = []

    if scanner_exit_code != 0:
        failure_reasons.append(f"scanner_exit_code={scanner_exit_code}")
    if timed_out:
        failure_reasons.append("scanner_timeout")

    if not run_skipped_weekend:
        if scanner_health is None:
            failure_reasons.append("fresh_scan_health_missing_or_invalid")
        elif scanner_collapsed:
            failure_reasons.append("scanner_reported_provider_collapse")

        if report_expected:
            if not report_audit.report_present:
                failure_reasons.append("fresh_scan_report_missing")
            elif report_audit.is_collapsed:
                failure_reasons.append("robust_provider_audit_collapsed")
            elif report_audit.is_degraded:
                warnings.append("robust_provider_audit_degraded")

    if not telegram_audit.delivery_verified:
        failure_reasons.append("telegram_delivery_not_verified")

    payload: dict[str, Any] = {
        "schema_version": 1,
        "scan_date": scan_date,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "scanner_exit_code": scanner_exit_code,
        "scanner_timed_out": timed_out,
        "run_skipped_weekend": run_skipped_weekend,
        "scanner_health_path": str(health_path) if health_path else None,
        "scanner_health_fresh": health_path is not None,
        "scanner_health": scanner_health,
        "scan_report_path": str(report_path) if report_path else None,
        "scan_report_fresh": report_path is not None,
        "report_expected": report_expected,
        "report_audit": asdict(report_audit),
        "telegram_audit": asdict(telegram_audit),
        "warnings": warnings,
        "failure_reasons": failure_reasons,
        "success": not failure_reasons,
    }
    atomic_write_json(run_health_path, payload)

    if run_skipped_weekend and not failure_reasons:
        print("[production-runner] PASS: intentional weekend skip")
    elif failure_reasons:
        print(
            "[production-runner] FAIL: " + ", ".join(failure_reasons),
            file=sys.stderr,
        )
    elif warnings:
        print("[production-runner] PASS WITH WARNING: " + ", ".join(warnings))
    else:
        print("[production-runner] PASS: scanner, provider health, and delivery checks passed")
    print(f"[production-runner] Health artifact: {run_health_path}")
    return _status_exit_code(failure_reasons)


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
