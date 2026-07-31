#!/usr/bin/env python3
"""Production reliability wrapper for the Dividend Quality Pullback scanner.

The existing scanner intentionally owns market-data and signal logic. This
wrapper adds operational truth around one execution without changing strategy:

- runs ``dividend_scanner.py`` with the original CLI arguments;
- validates the scanner health JSON and CSV report;
- detects DNS/TLS/provider collapse using the exact production error patterns;
- verifies Telegram success from the scanner's newly appended log records;
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
    signal_success_count: int
    signal_failure_count: int
    failure_line_count: int
    delivery_verified: bool


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
    wanted = set(keys)
    found = {key: False for key in wanted}
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
            value = value.strip().strip('"').strip("'")
            found[key] = bool(value)
    except OSError:
        return found
    return found


def telegram_credentials_present() -> bool:
    token_present = bool(os.getenv("TELEGRAM_TOKEN"))
    chat_present = bool(os.getenv("TELEGRAM_CHAT_ID"))
    if token_present and chat_present:
        return True
    dotenv = _read_dotenv_presence(
        REPO_ROOT / ".env", ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")
    )
    return dotenv["TELEGRAM_TOKEN"] and dotenv["TELEGRAM_CHAT_ID"]


def resolve_log_file() -> Path:
    configured = os.getenv("LOG_FILE")
    if not configured:
        env_values = _read_dotenv_values(REPO_ROOT / ".env", ("LOG_FILE",))
        configured = env_values.get("LOG_FILE")
    if not configured:
        return DEFAULT_LOG_FILE
    path = Path(configured).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


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


def _load_json(path: Path) -> dict[str, Any] | None:
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
) -> TelegramAudit:
    dry_run = _arg_present(args, "--dry-run")
    no_telegram = _arg_present(args, "--no-telegram")
    heartbeat_requested = _arg_present(args, "--daily-heartbeat")
    delivery_required = not dry_run and not no_telegram
    heartbeat_required = delivery_required and heartbeat_requested and not scanner_collapsed

    lines = log_delta.splitlines()
    explicit_failures = [
        line for line in lines if any(marker in line for marker in TELEGRAM_FAILURE_MARKERS)
    ]
    signal_failure_count = sum(
        1 for line in lines if re.search(r"Telegram alert for .+: FAILED\s*$", line)
    )
    signal_success_count = sum(
        1 for line in lines if re.search(r"Telegram alert for .+: sent\s*$", line)
    )
    heartbeat_claimed = any("Daily heartbeat sent." in line for line in lines)
    admin_warning_claimed = any("Admin Telegram warning sent." in line for line in lines)

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


def run(scanner_args: Sequence[str]) -> int:
    if not SCANNER_SCRIPT.exists():
        print(f"[production-runner] FAIL: missing {SCANNER_SCRIPT}", file=sys.stderr)
        return 20

    report_dir = resolve_report_dir(scanner_args)
    scan_date = datetime.now(NEW_YORK).date()
    health_path = report_dir / f"scan_health_{scan_date.isoformat()}.json"
    report_path = report_dir / f"scan_report_{scan_date.isoformat()}.csv"
    run_health_path = report_dir / f"run_health_{scan_date.isoformat()}.json"

    log_file = resolve_log_file()
    before_offset = log_offset(log_file)
    started_at = datetime.now(timezone.utc)

    completed = subprocess.run(
        [sys.executable, str(SCANNER_SCRIPT), *scanner_args],
        cwd=REPO_ROOT,
        check=False,
    )

    finished_at = datetime.now(timezone.utc)
    log_delta = read_log_delta(log_file, before_offset)
    scanner_health = _load_json(health_path)

    report_expected = _arg_present(scanner_args, "--report") and not _arg_present(
        scanner_args, "--no-report"
    )
    report_audit = audit_report(report_path) if report_expected else ReportAudit(
        report_path.exists(), 0, 0, 0, 0, 0.0, 0, False, False
    )

    scanner_collapsed = bool(scanner_health and scanner_health.get("is_collapsed"))
    telegram_audit = audit_telegram(
        log_delta=log_delta,
        args=scanner_args,
        scanner_collapsed=scanner_collapsed,
        credentials_present=telegram_credentials_present(),
    )

    failure_reasons: list[str] = []
    warnings: list[str] = []

    if completed.returncode != 0:
        failure_reasons.append(f"scanner_exit_code={completed.returncode}")
    if scanner_health is None:
        failure_reasons.append("scan_health_missing_or_invalid")
    elif scanner_collapsed:
        failure_reasons.append("scanner_reported_provider_collapse")

    if report_expected:
        if not report_audit.report_present:
            failure_reasons.append("scan_report_missing")
        elif report_audit.is_collapsed:
            failure_reasons.append("robust_provider_audit_collapsed")
        elif report_audit.is_degraded:
            warnings.append("robust_provider_audit_degraded")

    if not telegram_audit.delivery_verified:
        failure_reasons.append("telegram_delivery_not_verified")

    payload: dict[str, Any] = {
        "schema_version": 1,
        "scan_date": scan_date.isoformat(),
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "scanner_exit_code": completed.returncode,
        "scanner_health_path": str(health_path),
        "scanner_health": scanner_health,
        "scan_report_path": str(report_path),
        "report_expected": report_expected,
        "report_audit": asdict(report_audit),
        "telegram_audit": asdict(telegram_audit),
        "warnings": warnings,
        "failure_reasons": failure_reasons,
        "success": not failure_reasons,
    }
    atomic_write_json(run_health_path, payload)

    if failure_reasons:
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
