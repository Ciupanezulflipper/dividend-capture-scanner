#!/usr/bin/env python3
"""Android and Termux runtime checks for the operational gate."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tools.termux_gate_core import Runner, check, run


def crond_audit(runner: Runner = run) -> dict[str, Any]:
    code, stdout, stderr = runner(["pgrep", "-a", "crond"])
    if code == 0 and stdout.strip():
        return check("crond_process", "PASS", True, stdout.strip())
    _, ps_out, ps_err = runner(["ps", "-A"])
    lines = [line for line in ps_out.splitlines() if re.search(r"\bcrond\b", line)]
    return check(
        "crond_process",
        "PASS" if lines else "FAIL",
        True,
        " | ".join(lines[:3]) if lines else (stderr or ps_err or "crond not running").strip(),
    )


def timezone_audit(
    expected: str,
    variables: dict[str, str],
    runner: Runner = run,
    now: datetime | None = None,
) -> dict[str, Any]:
    cron_tz = variables.get("CRON_TZ") or variables.get("TZ")
    if cron_tz:
        return check(
            "cron_timezone",
            "PASS" if cron_tz == expected else "FAIL",
            True,
            f"crontab={cron_tz} expected={expected}",
            source="crontab",
        )
    code, stdout, _ = runner(["getprop", "persist.sys.timezone"])
    device_tz = stdout.strip() if code == 0 else ""
    if device_tz:
        return check(
            "cron_timezone",
            "PASS" if device_tz == expected else "FAIL",
            True,
            f"device={device_tz} expected={expected}",
            source="getprop",
        )
    local = now or datetime.now().astimezone()
    expected_now = local.astimezone(ZoneInfo(expected))
    same = local.utcoffset() == expected_now.utcoffset()
    return check(
        "cron_timezone",
        "WARN" if same else "FAIL",
        not same,
        f"exact zone unavailable; local={local.tzname()} {local.strftime('%z')} expected={expected_now.strftime('%z')}",
        source="offset_fallback",
    )


def boot_audit(home: Path) -> list[dict[str, Any]]:
    directory = home / ".termux" / "boot"
    scripts = sorted(path for path in directory.glob("*") if path.is_file()) if directory.is_dir() else []
    active: list[str] = []
    for script in scripts:
        try:
            lines = script.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        active.extend(
            re.sub(r"\s+#.*$", "", line)
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        )
    text = "\n".join(active)
    crond = re.search(r"(?:^|[;&|\s])crond(?:\s|$)", text) is not None
    wake = "termux-wake-lock" in text
    evidence = {"directory": str(directory), "scripts": [str(path) for path in scripts]}
    return [
        check("boot_starts_crond", "PASS" if crond else "FAIL", True, "hook found" if crond else "hook missing", **evidence),
        check("boot_acquires_wake_lock", "PASS" if wake else "FAIL", True, "hook found" if wake else "hook missing", **evidence),
    ]


def wake_audit(acquire: bool, runner: Runner = run) -> dict[str, Any]:
    command = shutil.which("termux-wake-lock")
    if not command:
        return check("wake_lock_request", "FAIL" if acquire else "WARN", acquire, "command not found")
    if not acquire:
        return check("wake_lock_request", "WARN", False, f"available={command}; not requested")
    code, stdout, stderr = runner([command])
    return check(
        "wake_lock_request",
        "PASS" if code == 0 else "FAIL",
        True,
        "request succeeded" if code == 0 else (stderr or stdout or "request failed").strip(),
    )


def battery_audit(runner: Runner = run) -> dict[str, Any]:
    code, stdout, stderr = runner(["cmd", "deviceidle", "whitelist"])
    if code:
        return check("battery_allowlist", "WARN", False, f"unverified: {(stderr or stdout).strip()}")
    allowed = "com.termux" in stdout
    return check(
        "battery_allowlist",
        "PASS" if allowed else "WARN",
        False,
        "com.termux listed" if allowed else "com.termux not shown",
    )


def git_audit(repo: Path, expected: str, runner: Runner = run) -> list[dict[str, Any]]:
    h_code, h_out, h_err = runner(["git", "-C", str(repo), "rev-parse", "HEAD"])
    s_code, s_out, s_err = runner(["git", "-C", str(repo), "status", "--porcelain"])
    head = h_out.strip() if h_code == 0 else ""
    return [
        check("git_head", "PASS" if head and (not expected or head == expected) else "FAIL", True, f"head={head or h_err.strip()} expected={expected or '<any>'}"),
        check("git_worktree", "PASS" if s_code == 0 and not s_out.strip() else "FAIL", True, "clean" if s_code == 0 and not s_out.strip() else (s_out or s_err).strip()),
    ]


def latest_health(repo: Path) -> dict[str, Any]:
    files = list(repo.glob("run_health_*.json"))
    reports = repo / "reports"
    if reports.is_dir():
        files.extend(reports.rglob("run_health_*.json"))
    files = [path for path in files if path.is_file()]
    if not files:
        return check("latest_run_health", "WARN", False, "not found")
    path = max(files, key=lambda item: item.stat().st_mtime)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return check("latest_run_health", "WARN", False, f"invalid: {exc}", path=str(path))
    status = str(payload.get("status") or payload.get("validation_status") or "unknown")
    good = status.lower() in {"pass", "passed", "success", "healthy"}
    return check("latest_run_health", "PASS" if good else "WARN", False, f"status={status}", path=str(path))
