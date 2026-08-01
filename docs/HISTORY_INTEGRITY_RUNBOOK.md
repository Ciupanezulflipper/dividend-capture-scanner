# Alert-History Integrity Runbook

This runbook covers only `history.json`, its crash-safe backup, corruption
evidence, and explicit recovery. It does not change or evaluate signal logic.

## Runtime files

For a default installation in the repository root:

- `history.json` — primary delivered-alert history.
- `history.json.last-good` — crash-safe backup snapshot.
- `history.json.recovery-required` — persistent fail-closed marker.
- `history*.corrupt.*` — quarantined invalid or conflicting evidence.

These files are runtime state and are ignored by Git.

## Normal behavior

On a successful alert delivery, the scanner writes the complete history snapshot
atomically to the backup and then the primary file. Both copies are flushed and
replaced in the same directory.

At startup, before any market-data request, the scanner validates both copies:

- A missing backup is rebuilt from a valid primary.
- A missing or corrupt primary is restored from a valid backup.
- A strict superset is treated as the newer monotonic snapshot and repairs the
  older copy.
- Conflicting existing entries, equal-size divergent snapshots, or loss of both
  valid copies cause a fail-closed exit with code `2`.

A fail-closed run sends no signal and performs no market-data scan. The recovery
marker remains until a valid snapshot is restored.

## Inspect current state

From the repository root:

```bash
python3 -m tools.history_recovery --history-file history.json status
```

Review:

- `history.valid` and `history.entries`
- `backup.valid` and `backup.entries`
- `recovery_marker.exists`
- `quarantine_files`

The status command does not modify any file.

## Select a recovery source

Use only a JSON file whose root is an alert-history object and whose values are
objects representing alert records. Do not use the recovery-marker JSON as a
source.

Validate a candidate without changing production state:

```bash
python3 - "<candidate-file>" <<'PY'
import json
import sys
from pathlib import Path
from history_store import validate_history_snapshot

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
history = validate_history_snapshot(payload)
print(f"CANDIDATE_STATUS=VALID entries={len(history)} path={path}")
PY
```

Choose the trustworthy candidate with the most complete delivered-alert set.
When two candidates disagree on an existing alert key, do not merge them by
hand without first establishing which record is authoritative.

## Restore explicitly

The restore command requires `--force`, validates the source, atomically rebuilds
both snapshots, clears the marker only after successful writes, reloads the
result, and verifies exact equality.

```bash
python3 -m tools.history_recovery \
  --history-file history.json \
  restore \
  --from-file "<candidate-file>" \
  --force
```

Required success output:

```text
RESTORE_STATUS=PASSED entries=<N> source=<candidate-file>
```

Then inspect again:

```bash
python3 -m tools.history_recovery --history-file history.json status
```

Acceptance conditions:

- primary and backup both exist;
- both are valid;
- both have the same entry count;
- `recovery_marker.exists` is `false`.

## Post-recovery no-send validation

Run a small market-data test without Telegram or history writes:

```bash
./run_bot.sh \
  --dry-run \
  --limit 50 \
  --force-weekend \
  --report \
  --report-dir "reports/history-recovery-smoke-$(date +%Y%m%d-%H%M%S)" \
  --sleep-seconds 0
```

A dry run intentionally does not load or write production history. Its purpose
is to confirm that the scanner and provider wrapper remain operational after the
recovery procedure. The next live scheduled run is the first proof that normal
deduplication resumed.

## Prohibited shortcuts

Do not:

- delete `history.json.recovery-required` merely to make the scanner start;
- replace `history.json` with `{}` unless the delivered-alert history is truly
  known to be empty;
- copy the recovery-marker JSON into `history.json`;
- edit primary and backup independently;
- remove quarantine evidence before recovery is verified.

Those shortcuts can cause previously delivered alerts to be sent again.
