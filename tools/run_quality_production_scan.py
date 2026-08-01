#!/usr/bin/env python3
"""Run the audit-enhanced scanner through the existing production wrapper."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import run_production_scan as production  # noqa: E402

production.SCANNER_SCRIPT = REPO_ROOT / "quality_scanner.py"

if __name__ == "__main__":
    raise SystemExit(production.run(sys.argv[1:]))
