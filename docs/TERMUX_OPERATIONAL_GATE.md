# Termux Operational Gate

`tools/termux_operational_gate.py` audits whether the production scanner is actually positioned to run unattended on Android. Its default mode is read-only.

## What it verifies

- the production Git head and clean worktree;
- valid, semantically identical `history.json` and `history.json.last-good` snapshots;
- an exact cron schedule that invokes the production `run_bot.sh` path;
- required cron arguments such as `--daily-heartbeat` and `--report`;
- a running `crond` process;
- the explicitly configured cron timezone from `CRON_TZ`, `TZ`, or Android `getprop`;
- Termux:Boot scripts that start `crond` and request `termux-wake-lock`;
- availability and optional execution of `termux-wake-lock`;
- Android device-idle allowlist evidence when the local shell permits it;
- the latest production-wrapper health artifact, including dated subdirectories below `reports/`.

Unknown Android permission state is reported as `WARN`; it is never silently reported as passed.

## History semantics

The primary and last-good snapshots may use different whitespace or key formatting. The gate validates and compares their parsed JSON objects for semantic equality. It separately records each file's SHA-256 hash and requires both individual hashes to remain unchanged across a Telegram canary.

## Telegram canary

`--telegram-canary` sends exactly one message by calling `telegram_delivery.send_telegram` directly. It does not invoke the scanner, does not fetch market data, and does not write signal history.

Before sending, the tool requires both history snapshots to be valid and semantically identical. It hashes each file before and after the send and fails the canary if either byte sequence changes.

The canary reads `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` only from its process environment. It does not parse or copy `.env` into the evidence file. The production invocation below loads `.env` inside a subprocess environment.

The canary validates Telegram's JSON `ok: true` response through the production delivery contract. Credentials and message contents are not written to the JSON evidence file, and token-like values found in cron output are redacted.

## Production invocation

The current production crontab explicitly declares `CRON_TZ=UTC`, so the audit must verify UTC unless the schedule itself is intentionally changed.

```bash
python3 -m tools.termux_operational_gate \
  --expected-head <DEPLOYED_MAIN_SHA> \
  --expected-cron-timezone UTC \
  --expected-cron '0 10 * * 1-5' \
  --require-cron-arg=--daily-heartbeat \
  --require-cron-arg=--report \
  --acquire-wake-lock \
  --telegram-canary
```

The default evidence path is `reports/operational_gate_latest.json`.

## Exit codes

- `0`: no critical failure; warnings may still require operator attention.
- `23`: the canary reached Telegram but delivery was not verified.
- `30`: a critical operational prerequisite failed or blocked the canary.

## Android limitation

A user-initiated Android **Force stop** prevents Termux processes and scheduled work from running until Termux is opened again. This gate verifies current `crond`, wake-lock request, battery evidence, and reboot hooks; it cannot make a force-stopped app continue executing.

## Scope

This tool does not edit crontab, create boot scripts, change Android settings, start the scanner, change strategy thresholds, or mutate history. Any repair is a separate supervised operation based on the generated evidence.
