#!/usr/bin/env python3
"""Audit unattended Termux execution and optionally send one direct canary."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from telegram_delivery import TelegramDeliveryResult, send_telegram
from tools.termux_gate_core import atomic_json, check, cron_audit, history_pair
from tools.termux_gate_runtime import (
    battery_audit,
    boot_audit,
    crond_audit,
    git_audit,
    latest_health,
    timezone_audit,
    wake_audit,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TZ = "America/New_York"
DEFAULT_CRON = "0 10 * * 1-5"


def canary(
    repo: Path,
    expected_head: str,
    logger: logging.Logger,
    post: Callable[..., Any] | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any], TelegramDeliveryResult | None]:
    history_check, before = history_pair(repo)
    if history_check["status"] != "PASS":
        return check("telegram_canary", "FAIL", True, f"blocked: {history_check['detail']}"), None
    token = os.getenv("TELEGRAM_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    stamp = (now or datetime.now(timezone.utc)).astimezone().isoformat(timespec="seconds")
    result = send_telegram(
        token,
        chat,
        "DQP operational canary\n"
        f"Time: {stamp}\nHead: {expected_head or 'unconstrained'}\n"
        "Direct delivery test only; scanner and history were not invoked.",
        logger,
        kind="canary",
        subject=stamp,
        required=True,
        post=post,
    )
    _, after = history_pair(repo)
    unchanged = before == after and bool(before)
    passed = result.delivered and unchanged
    return (
        check(
            "telegram_canary",
            "PASS" if passed else "FAIL",
            True,
            f"outcome={result.outcome} delivered={str(result.delivered).lower()} history_unchanged={str(unchanged).lower()}",
            attempted=result.attempted,
            delivered=result.delivered,
            outcome=result.outcome,
            status_code=result.status_code,
            history_unchanged=unchanged,
        ),
        result,
    )


def overall(checks: Sequence[dict[str, Any]]) -> str:
    if any(item["critical"] and item["status"] == "FAIL" for item in checks):
        return "FAIL"
    return "PASS_WITH_WARNINGS" if any(item["status"] in {"WARN", "FAIL"} for item in checks) else "PASS"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--repo", type=Path, default=ROOT)
    result.add_argument("--expected-head", default="")
    result.add_argument("--expected-timezone", default=DEFAULT_TZ)
    result.add_argument("--expected-cron", default=DEFAULT_CRON)
    result.add_argument("--require-cron-arg", action="append", default=[])
    result.add_argument("--acquire-wake-lock", action="store_true")
    result.add_argument("--telegram-canary", action="store_true")
    result.add_argument("--output", type=Path, default=ROOT / "reports" / "operational_gate_latest.json")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo = args.repo.resolve()
    logger = logging.getLogger("termux_operational_gate")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler(sys.stderr))
    logger.setLevel(logging.INFO)

    checks = git_audit(repo, args.expected_head)
    history_check, _ = history_pair(repo)
    checks.append(history_check)
    cron_check, variables = cron_audit(repo, args.expected_cron, args.require_cron_arg)
    checks.extend([cron_check, crond_audit(), timezone_audit(args.expected_timezone, variables)])
    checks.extend(boot_audit(Path.home()))
    checks.extend([wake_audit(args.acquire_wake_lock), battery_audit(), latest_health(repo)])

    delivery: TelegramDeliveryResult | None = None
    if args.telegram_canary:
        canary_check, delivery = canary(repo, args.expected_head, logger)
        checks.append(canary_check)
    else:
        checks.append(check("telegram_canary", "SKIP", False, "not requested"))

    status = overall(checks)
    output = args.output if args.output.is_absolute() else repo / args.output
    atomic_json(
        output,
        {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repo": str(repo),
            "status": status,
            "expected_head": args.expected_head,
            "expected_timezone": args.expected_timezone,
            "expected_cron": args.expected_cron,
            "required_cron_args": args.require_cron_arg,
            "checks": checks,
            "telegram_result": delivery.__dict__ if delivery else None,
        },
    )
    for item in checks:
        print(
            f"CHECK name={item['name']} status={item['status']} "
            f"critical={str(item['critical']).lower()} detail={item['detail']}"
        )
    print(f"OPERATIONAL_GATE_STATUS={status}")
    print(
        "TELEGRAM_CANARY_STATUS="
        + ("DELIVERED" if delivery and delivery.delivered else "FAILED" if args.telegram_canary else "SKIPPED")
    )
    print(f"EVIDENCE_FILE={output}")
    if args.telegram_canary and (not delivery or not delivery.delivered):
        return 23
    return 30 if status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
