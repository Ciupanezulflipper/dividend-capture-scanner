#!/usr/bin/env python3
"""One-time deterministic refactor for history_store integration.

Every replacement asserts the exact merged-main source anchor. The script aborts
rather than guessing if the file has drifted.
"""

from __future__ import annotations

from pathlib import Path

SCANNER = Path(__file__).resolve().parent.parent / "dividend_scanner.py"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one exact anchor, found {count}")
    return source.replace(old, new, 1)


def main() -> None:
    source = SCANNER.read_text(encoding="utf-8")

    source = replace_once(
        source,
        "from typing import Any, Optional\n\nimport pandas as pd\n",
        "from typing import Any, Optional\n\n"
        "from history_store import HistoryRecoveryRequired, load_history, save_history\n\n"
        "import pandas as pd\n",
        "history_store import",
    )

    source = replace_once(
        source,
        '''# ── History (deduplication) ───────────────────────────────────────────────────\n\ndef load_history(path: Path) -> dict:\n    if path.exists():\n        try:\n            return json.loads(path.read_text(encoding="utf-8"))\n        except Exception:\n            return {}\n    return {}\n\n\ndef save_history(path: Path, history: dict) -> None:\n    path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")\n\n\n''',
        '''# ── History (deduplication) ───────────────────────────────────────────────────\n# Crash-safe load/save operations are implemented in history_store.py.\n\n\n''',
        "inline history functions",
    )

    source = replace_once(
        source,
        "    history = {} if args.dry_run else load_history(HISTORY_FILE)\n",
        '''    if args.dry_run:\n        history = {}\n    else:\n        try:\n            history = load_history(HISTORY_FILE, logger=logger)\n        except HistoryRecoveryRequired as exc:\n            logger.critical("HISTORY_RECOVERY_REQUIRED | %s", exc)\n            console.print(\n                "[bold red]HISTORY_RECOVERY_REQUIRED[/bold red] — "\n                "no valid alert-history snapshot remains. "\n                "Signals are blocked until history is recovered."\n            )\n            raise SystemExit(2) from exc\n''',
        "history load call",
    )

    source = replace_once(
        source,
        "            save_history(HISTORY_FILE, history)\n",
        "            save_history(HISTORY_FILE, history, logger=logger)\n",
        "history save call",
    )

    SCANNER.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
