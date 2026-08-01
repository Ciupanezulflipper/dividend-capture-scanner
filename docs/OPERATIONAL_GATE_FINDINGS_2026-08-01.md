# Operational Gate Findings — 2026-08-01

Production deployment `04cfb1dc4f39524605f808f9d21f09fa93da8c30` completed successfully on Termux and the full 57-test suite passed.

The first live gate produced two critical findings and two warnings:

- `history_pair=FAIL`: both snapshots were valid with 19 entries, but the gate compared raw file hashes. This is not sufficient evidence of semantic divergence because the primary file was deliberately preserved while the last-good file was written in canonical JSON formatting.
- `cron_timezone=FAIL`: the live crontab explicitly declares `CRON_TZ=UTC`. The audit invocation incorrectly expected `America/New_York`; the cron entry itself matched the exact required schedule and arguments.
- `latest_run_health=WARN`: the gate searched only the repository root and the immediate `reports/` directory, while production writes health files into dated report subdirectories.
- `battery_allowlist=WARN`: Android denied access to `DeviceIdleController` state because the Termux shell lacks `android.permission.DUMP`. This is an explicit unknown, not evidence that Termux is excluded.

The Telegram canary was blocked before any network request because the gate treated raw-byte history inequality as a critical failure. No Telegram message was attempted and neither history file changed.

Follow-up changes must:

1. compare parsed, validated history objects for semantic equality while retaining per-file hashes for before/after immutability checks;
2. discover health artifacts recursively below `reports/`;
3. audit the currently configured cron timezone as `UTC` unless the production schedule itself is intentionally changed;
4. distinguish a canary blocked by prerequisite failures from an attempted Telegram delivery failure.
