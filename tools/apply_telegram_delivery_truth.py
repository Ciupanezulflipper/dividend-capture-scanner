#!/usr/bin/env python3
"""One-time exact-anchor refactor for truthful Telegram delivery handling."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"anchor count for {path}: expected 1, got {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_scanner() -> None:
    path = ROOT / "dividend_scanner.py"
    replace_once(
        path,
        "from history_store import HistoryRecoveryRequired, load_history, save_history\n",
        "from history_store import HistoryRecoveryRequired, load_history, save_history\n"
        "from telegram_delivery import send_telegram\n",
    )

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(# ── Telegram ─+\n\n)"
        r"def send_telegram\(token: str, chat_id: str, text: str, logger: logging\.Logger\) -> bool:\n"
        r".*?"
        r"(?=def build_telegram_message\()",
        re.DOTALL,
    )
    text, count = pattern.subn(r"\1", text, count=1)
    if count != 1:
        raise SystemExit(f"inline send_telegram removal count: expected 1, got {count}")
    path.write_text(text, encoding="utf-8")

    replace_once(
        path,
        '''        if not args.dry_run and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            admin_msg = (
                f"\\u26a0\\ufe0f SCANNER: DATA_PROVIDER_FAILURE\\n"
                f"Date: {today}\\n"
                f"Provider error rate: {run_quality['provider_failure_rate'] * 100:.1f}%\\n"
                f"Usable ex-dates: {run_quality['usable_ex_date']}/{run_quality['total']}\\n"
                f"History write: BLOCKED\\n"
                f"Signals sent: 0"
            )
            send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, admin_msg, logger)
            logger.info("Admin Telegram warning sent.")
        if report_path is not None:
            console.print(f"[cyan]Audit report:[/cyan] {report_path}")
        sys.exit(0)
''',
        '''        admin_delivery_failed = False
        if not args.dry_run and not args.no_telegram:
            admin_msg = (
                f"\\u26a0\\ufe0f SCANNER: DATA_PROVIDER_FAILURE\\n"
                f"Date: {today}\\n"
                f"Provider error rate: {run_quality['provider_failure_rate'] * 100:.1f}%\\n"
                f"Usable ex-dates: {run_quality['usable_ex_date']}/{run_quality['total']}\\n"
                f"History write: BLOCKED\\n"
                f"Signals sent: 0"
            )
            admin_result = send_telegram(
                TELEGRAM_TOKEN,
                TELEGRAM_CHAT_ID,
                admin_msg,
                logger,
                kind="admin_warning",
                subject="DATA_PROVIDER_FAILURE",
            )
            admin_delivery_failed = not admin_result.delivered
        if report_path is not None:
            console.print(f"[cyan]Audit report:[/cyan] {report_path}")
        if admin_delivery_failed:
            raise SystemExit(23)
        sys.exit(0)
''',
    )

    replace_once(
        path,
        '''    delivered: list[str] = []

    for sig in signals:
''',
        '''    delivered: list[str] = []
    required_delivery_failures: list[str] = []

    for sig in signals:
''',
    )

    replace_once(
        path,
        '''                sent = send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg, logger)
                logger.info(
                    "Telegram alert for %s: %s",
                    sym,
                    "sent" if sent else "FAILED",
                )
                if sent:
                    record_alert(history, sym, ex, {
''',
        '''                signal_result = send_telegram(
                    TELEGRAM_TOKEN,
                    TELEGRAM_CHAT_ID,
                    msg,
                    logger,
                    kind="signal",
                    subject=sym,
                )
                if signal_result.delivered:
                    record_alert(history, sym, ex, {
''',
    )

    replace_once(
        path,
        '''                    delivered.append(sym)
        else:
            logger.debug("%s already alerted for ex-date %s.", sym, ex)
''',
        '''                    delivered.append(sym)
                else:
                    required_delivery_failures.append(f"signal:{sym}")
        else:
            logger.debug("%s already alerted for ex-date %s.", sym, ex)
''',
    )

    replace_once(
        path,
        '''    if args.daily_heartbeat and not args.dry_run and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
''',
        '''    if args.daily_heartbeat and not args.dry_run and not args.no_telegram:
''',
    )

    replace_once(
        path,
        '''        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, hb_msg, logger)
        logger.info("Daily heartbeat sent.")
''',
        '''        heartbeat_result = send_telegram(
            TELEGRAM_TOKEN,
            TELEGRAM_CHAT_ID,
            hb_msg,
            logger,
            kind="heartbeat",
            subject=str(today),
        )
        if not heartbeat_result.delivered:
            required_delivery_failures.append("heartbeat")
''',
    )

    replace_once(
        path,
        '''    if report_path is not None:
        console.print(f"[cyan]Audit report:[/cyan] {report_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────
''',
        '''    if report_path is not None:
        console.print(f"[cyan]Audit report:[/cyan] {report_path}")

    if required_delivery_failures:
        logger.error(
            "TELEGRAM_REQUIRED_DELIVERY_FAILED count=%d items=%s",
            len(required_delivery_failures),
            ",".join(required_delivery_failures),
        )
        raise SystemExit(23)


# ── CLI ───────────────────────────────────────────────────────────────────────
''',
    )


def patch_runner() -> None:
    path = ROOT / "tools" / "run_production_scan.py"
    replace_once(
        path,
        '''TELEGRAM_FAILURE_MARKERS = (
    "Telegram send failed:",
    "Telegram API error ",
)
''',
        '''TELEGRAM_FAILURE_MARKERS = (
    "Telegram send failed:",
    "Telegram API error ",
)
TELEGRAM_LOG_PREFIX = "TELEGRAM_DELIVERY "
''',
    )
    replace_once(
        path,
        '''    signal_failure_count: int
    failure_line_count: int
    delivery_verified: bool
''',
        '''    signal_failure_count: int
    required_failure_count: int
    failure_line_count: int
    delivery_verified: bool
''',
    )
    replace_once(
        path,
        '''def audit_telegram(
''',
        '''def parse_structured_telegram_deliveries(log_delta: str) -> list[dict[str, Any]]:
    deliveries: list[dict[str, Any]] = []
    for line in log_delta.splitlines():
        marker_index = line.find(TELEGRAM_LOG_PREFIX)
        if marker_index < 0:
            continue
        raw = line[marker_index + len(TELEGRAM_LOG_PREFIX) :].strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            deliveries.append(payload)
    return deliveries


def audit_telegram(
''',
    )

    start = path.read_text(encoding="utf-8")
    old = '''    lines = log_delta.splitlines()
    explicit_failures = [
        line for line in lines if any(marker in line for marker in TELEGRAM_FAILURE_MARKERS)
    ]
    signal_attempt_count = sum(1 for line in lines if "Telegram alert for " in line)
    signal_failure_count = sum(
        1 for line in lines if re.search(r"Telegram alert for .+: FAILED\\s*$", line)
    )
    signal_success_count = sum(
        1 for line in lines if re.search(r"Telegram alert for .+: sent\\s*$", line)
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
'''
    new = '''    lines = log_delta.splitlines()
    explicit_failures = [
        line for line in lines if any(marker in line for marker in TELEGRAM_FAILURE_MARKERS)
    ]
    structured = parse_structured_telegram_deliveries(log_delta)
    required_failures = [
        item
        for item in structured
        if item.get("required") is True and item.get("delivered") is not True
    ]

    if structured:
        signal_records = [item for item in structured if item.get("kind") == "signal"]
        signal_attempt_count = sum(item.get("attempted") is True for item in signal_records)
        signal_failure_count = sum(item.get("delivered") is not True for item in signal_records)
        signal_success_count = sum(item.get("delivered") is True for item in signal_records)
        heartbeat_claimed = any(
            item.get("kind") == "heartbeat" and item.get("delivered") is True
            for item in structured
        )
        admin_warning_claimed = any(
            item.get("kind") == "admin_warning" and item.get("delivered") is True
            for item in structured
        )
    else:
        signal_attempt_count = sum(1 for line in lines if "Telegram alert for " in line)
        signal_failure_count = sum(
            1 for line in lines if re.search(r"Telegram alert for .+: FAILED\\s*$", line)
        )
        signal_success_count = sum(
            1 for line in lines if re.search(r"Telegram alert for .+: sent\\s*$", line)
        )
        heartbeat_claimed = any("Daily heartbeat sent." in line for line in lines)
        admin_warning_claimed = any("Admin Telegram warning sent." in line for line in lines)

    live_telegram_allowed = not dry_run and not no_telegram and not run_skipped
    delivery_required = live_telegram_allowed and (
        heartbeat_requested
        or scanner_collapsed
        or signal_attempt_count > 0
        or any(item.get("required") is True for item in structured)
    )
    heartbeat_required = delivery_required and heartbeat_requested and not scanner_collapsed

    delivery_verified = True
    if delivery_required and not credentials_present:
        delivery_verified = False
    if explicit_failures or signal_failure_count or required_failures:
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
        required_failure_count=len(required_failures),
        failure_line_count=len(explicit_failures) + len(required_failures),
        delivery_verified=delivery_verified,
    )
'''
    if start.count(old) != 1:
        raise SystemExit(f"audit_telegram body anchor count: {start.count(old)}")
    path.write_text(start.replace(old, new, 1), encoding="utf-8")

    replace_once(
        path,
        '''    if any(reason.startswith("scanner_exit_code=") for reason in failure_reasons):
        return 20
''',
        '''    if "scanner_exit_code=23" in failure_reasons or any(
        "telegram" in reason for reason in failure_reasons
    ):
        return 23
    if any(reason.startswith("scanner_exit_code=") for reason in failure_reasons):
        return 20
''',
    )


def patch_runner_tests() -> None:
    path = ROOT / "tests" / "test_production_runner.py"
    replace_once(path, "import csv\n", "import csv\nimport json\n")
    replace_once(
        path,
        '''    audit_report,
    audit_telegram,
''',
        '''    _status_exit_code,
    audit_report,
    audit_telegram,
''',
    )
    replace_once(
        path,
        '''    def test_dry_run_does_not_require_telegram(self) -> None:
        result = audit_telegram(
            "",
            ["--dry-run", "--daily-heartbeat"],
            scanner_collapsed=False,
            credentials_present=False,
        )
        self.assertFalse(result.delivery_required)
        self.assertTrue(result.delivery_verified)


if __name__ == "__main__":
''',
        '''    def test_dry_run_does_not_require_telegram(self) -> None:
        result = audit_telegram(
            "",
            ["--dry-run", "--daily-heartbeat"],
            scanner_collapsed=False,
            credentials_present=False,
        )
        self.assertFalse(result.delivery_required)
        self.assertTrue(result.delivery_verified)

    def test_structured_heartbeat_success_is_verified(self) -> None:
        payload = {
            "kind": "heartbeat",
            "subject": "2026-07-31",
            "required": True,
            "attempted": True,
            "delivered": True,
            "outcome": "delivered",
            "status_code": 200,
            "detail": "",
        }
        result = audit_telegram(
            "TELEGRAM_DELIVERY " + json.dumps(payload),
            ["--daily-heartbeat"],
            scanner_collapsed=False,
            credentials_present=True,
        )
        self.assertTrue(result.heartbeat_claimed)
        self.assertTrue(result.delivery_verified)
        self.assertEqual(result.required_failure_count, 0)

    def test_structured_required_failure_is_rejected(self) -> None:
        payload = {
            "kind": "admin_warning",
            "subject": "DATA_PROVIDER_FAILURE",
            "required": True,
            "attempted": True,
            "delivered": False,
            "outcome": "transport_error",
            "status_code": None,
            "detail": "NameResolutionError",
        }
        result = audit_telegram(
            "TELEGRAM_DELIVERY " + json.dumps(payload),
            [],
            scanner_collapsed=True,
            credentials_present=True,
        )
        self.assertFalse(result.admin_warning_claimed)
        self.assertFalse(result.delivery_verified)
        self.assertEqual(result.required_failure_count, 1)

    def test_scanner_exit_23_remains_telegram_exit_23(self) -> None:
        self.assertEqual(
            _status_exit_code(
                ["scanner_exit_code=23", "telegram_delivery_not_verified"]
            ),
            23,
        )


if __name__ == "__main__":
''',
    )


def patch_ci() -> None:
    path = ROOT / ".github" / "workflows" / "scanner-reliability.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '      - "history_store.py"\n',
        '      - "history_store.py"\n      - "telegram_delivery.py"\n',
    )
    if text.count('      - "telegram_delivery.py"\n') != 2:
        raise SystemExit("expected telegram_delivery.py in both CI path lists")
    text = text.replace(
        '      - "tests/test_scanner_history_integration.py"\n',
        '      - "tests/test_scanner_history_integration.py"\n'
        '      - "tests/test_scanner_telegram_integration.py"\n'
        '      - "tests/test_telegram_delivery.py"\n',
    )
    if text.count('      - "tests/test_telegram_delivery.py"\n') != 2:
        raise SystemExit("expected Telegram tests in both CI path lists")
    text = text.replace(
        '          history_store.py\n',
        '          history_store.py\n          telegram_delivery.py\n',
        1,
    )
    text = text.replace(
        '          tests/test_scanner_history_integration.py\n',
        '          tests/test_scanner_history_integration.py\n'
        '          tests/test_scanner_telegram_integration.py\n'
        '          tests/test_telegram_delivery.py\n',
        1,
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_scanner()
    patch_runner()
    patch_runner_tests()
    patch_ci()


if __name__ == "__main__":
    main()
