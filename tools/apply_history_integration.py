#!/usr/bin/env python3
"""One-time deterministic refactor to fail on history state before network I/O.

Revision 2 retriggers the exact transform from the latest branch head.
"""

from __future__ import annotations

from pathlib import Path

SCANNER = Path(__file__).resolve().parent.parent / "dividend_scanner.py"


def main() -> None:
    source = SCANNER.read_text(encoding="utf-8")
    old = '''    if not HAS_YFINANCE:\n        console.print("[red]yfinance not installed — cannot proceed.[/red]")\n        sys.exit(1)\n\n    tickers = fetch_sp500_tickers(logger)\n    if args.limit:\n        tickers = tickers[: args.limit]\n        logger.info("Limiting scan to first %d tickers.", args.limit)\n\n    if args.dry_run:\n        history = {}\n    else:\n        try:\n            history = load_history(HISTORY_FILE, logger=logger)\n        except HistoryRecoveryRequired as exc:\n            logger.critical("HISTORY_RECOVERY_REQUIRED | %s", exc)\n            console.print(\n                "[bold red]HISTORY_RECOVERY_REQUIRED[/bold red] — "\n                "no valid alert-history snapshot remains. "\n                "Signals are blocked until history is recovered."\n            )\n            raise SystemExit(2) from exc\n'''
    new = '''    if args.dry_run:\n        history = {}\n    else:\n        try:\n            history = load_history(HISTORY_FILE, logger=logger)\n        except HistoryRecoveryRequired as exc:\n            logger.critical("HISTORY_RECOVERY_REQUIRED | %s", exc)\n            console.print(\n                "[bold red]HISTORY_RECOVERY_REQUIRED[/bold red] — "\n                "no valid alert-history snapshot remains. "\n                "Signals are blocked until history is recovered."\n            )\n            raise SystemExit(2) from exc\n\n    if not HAS_YFINANCE:\n        console.print("[red]yfinance not installed — cannot proceed.[/red]")\n        sys.exit(1)\n\n    tickers = fetch_sp500_tickers(logger)\n    if args.limit:\n        tickers = tickers[: args.limit]\n        logger.info("Limiting scan to first %d tickers.", args.limit)\n'''
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"history-before-network anchor: expected one, found {count}")
    SCANNER.write_text(source.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    main()
