# CONTINUITY.md

## Current Verified State — 2026-05-01

- GitHub repo: Ciupanezulflipper/dividend-capture-scanner
- Visibility: private
- Local path: /data/data/com.termux/files/home/dividend-capture-scanner
- Git protocol: SSH
- Control files created: YES
- dividend_scanner.py created: YES
- requirements.txt created: YES
- run_bot.sh created: YES
- Python syntax: PASS
- Bash syntax: PASS
- Termux smoke test: PASS
- Commit created: NO
- Push done: NO

## Latest Smoke Test

Command:

    ./run_bot.sh --dry-run --limit 10 --show-all

Verified:
- Scanner started.
- S&P 500 list loaded.
- Limit 10 worked.
- Rich dashboard rendered.
- Telegram not sent in dry-run.
- history.json not created in dry-run.
- Result: PASS.

## Important Fixes Applied

- Removed lxml from core requirements.
- Removed pandas-ta from core requirements.
- Kept html5lib and beautifulsoup4 as core parser dependencies.
- Made lxml and pandas-ta optional in run_bot.sh.
- Added Termux auto-detection in run_bot.sh.
- Added .termux_req_sha256 to .gitignore.
- Forced pandas.read_html to use html5lib.
- Added requests.get with User-Agent for Wikipedia.
- Wrapped response.text in StringIO.
- Added missing StringIO import.

## Next Step

First commit and push after final pre-commit verification.
