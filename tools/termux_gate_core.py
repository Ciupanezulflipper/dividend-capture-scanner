#!/usr/bin/env python3
"""Shared primitives for the Termux operational gate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

Runner = Callable[[Sequence[str]], tuple[int, str, str]]


def run(args: Sequence[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout, check=False
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"


def check(name: str, status: str, critical: bool, detail: str, **evidence: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "critical": critical,
        "detail": detail,
        "evidence": evidence,
    }


def redact(value: str) -> str:
    text = str(value or "")
    text = re.sub(
        r"(?i)\b(TELEGRAM_TOKEN|BOT_TOKEN|API_TOKEN|TOKEN)=([^\s;]+)",
        lambda match: f"{match.group(1)}=[REDACTED]",
        text,
    )
    return re.sub(r"/bot[^/\s]+/", "/bot[REDACTED]/", text)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_valid_history(path: Path) -> tuple[bool, int, str, dict[str, Any] | None]:
    if not path.is_file():
        return False, 0, "missing", None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, 0, f"invalid_json:{type(exc).__name__}", None
    if not isinstance(payload, dict):
        return False, 0, "root_not_object", None
    if any(not isinstance(value, dict) for value in payload.values()):
        return False, len(payload), "non_object_entry", None
    return True, len(payload), "valid", payload


def valid_history(path: Path) -> tuple[bool, int, str]:
    valid, count, detail, _ = load_valid_history(path)
    return valid, count, detail


def history_pair(repo: Path) -> tuple[dict[str, Any], dict[str, str]]:
    primary, backup = repo / "history.json", repo / "history.json.last-good"
    p_ok, p_count, p_detail, p_payload = load_valid_history(primary)
    b_ok, b_count, b_detail, b_payload = load_valid_history(backup)
    hashes = {
        key: digest(path)
        for key, path in (("primary", primary), ("backup", backup))
        if path.is_file()
    }
    byte_equal = bool(hashes.get("primary")) and hashes.get("primary") == hashes.get("backup")
    semantic_equal = p_ok and b_ok and p_payload == b_payload
    passed = bool(semantic_equal)
    return (
        check(
            "history_pair",
            "PASS" if passed else "FAIL",
            True,
            (
                f"primary={p_detail}:{p_count} backup={b_detail}:{b_count} "
                f"semantic_equal={str(semantic_equal).lower()} "
                f"byte_equal={str(byte_equal).lower()}"
            ),
            primary=str(primary),
            backup=str(backup),
            primary_entries=p_count,
            backup_entries=b_count,
            semantic_equal=semantic_equal,
            byte_equal=byte_equal,
        ),
        hashes,
    )


def parse_crontab(text: str) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    variables: dict[str, str] = {}
    entries: list[tuple[str, str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        assignment = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if assignment:
            variables[assignment.group(1)] = assignment.group(2).strip().strip('"\'')
            continue
        parts = line.split(None, 1) if line.startswith("@") else line.split(None, 5)
        if len(parts) == 2 and line.startswith("@"):
            entries.append((parts[0], parts[1], raw))
        elif len(parts) == 6:
            entries.append((" ".join(parts[:5]), parts[5], raw))
    return variables, entries


def launcher_in(command: str, repo: Path) -> bool:
    launcher, root = str((repo / "run_bot.sh").resolve()), str(repo.resolve())
    return launcher in command or (
        root in command
        and re.search(r"(?:^|\s|/)\.?/?run_bot\.sh(?:\s|$)", command) is not None
    )


def cron_audit(
    repo: Path,
    expected: str,
    required_args: Iterable[str],
    runner: Runner = run,
) -> tuple[dict[str, Any], dict[str, str]]:
    code, stdout, stderr = runner(["crontab", "-l"])
    if code:
        return check("cron_entry", "FAIL", True, redact(stderr or stdout or "crontab unavailable")), {}
    variables, entries = parse_crontab(stdout)
    safe_vars = {
        key: "[REDACTED]" if re.search(r"(?i)(TOKEN|SECRET|PASSWORD|KEY)$", key) else value
        for key, value in variables.items()
    }
    evidence: list[dict[str, Any]] = []
    for schedule, command, raw in entries:
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        reasons = []
        if schedule != expected:
            reasons.append(f"schedule={schedule}")
        if not launcher_in(command, repo):
            reasons.append("launcher_path_missing")
        reasons.extend(f"missing_arg={arg}" for arg in required_args if arg not in tokens)
        evidence.append(
            {
                "schedule": schedule,
                "command": redact(command),
                "raw": redact(raw),
                "matched": not reasons,
                "reasons": reasons,
            }
        )
    matched = sum(item["matched"] for item in evidence)
    return (
        check(
            "cron_entry",
            "PASS" if matched else "FAIL",
            True,
            f"matched={matched} parsed={len(entries)} expected={expected}",
            variables=safe_vars,
            entries=evidence,
        ),
        variables,
    )
