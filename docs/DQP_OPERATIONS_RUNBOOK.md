# DQP Operations Runbook

Project: dividend-capture-scanner
Bot: TomaDividendQualityBot / Dividend Quality Pullback scanner
Termux repo path: /data/data/com.termux/files/home/dividend-capture-scanner
This is not BotA. BotA is the separate forex bot.

## Validated state — 2026-07-01

Scanner run: PASS
Telegram clean signals: PASS
Daily heartbeat: PASS
CSV report writing: PASS
Health JSON writing: PASS
CRON_TZ timing: confirmed by July 1 run at 16:18 Copenhagen / 10:18 New York window
crond package: cronie 1.7.2
BusyBox crond: NO

## Outage diagnosis — 2026-07-10 to 2026-07-22

**Symptom**: No Telegram heartbeat or signals after July 10.

**Observed failure mode**: During unattended cron runs at 10:00 AM NY, DNS
resolution failed for all external hosts (`query1.finance.yahoo.com`,
`en.wikipedia.org`, `api.telegram.org`), returning `[Errno 7] No address
associated with hostname`. The cron fired, the scanner ran, and audit reports
were written — but 100% provider errors occurred because no network was reachable.

**Cron/crond status**: healthy throughout. Reports written every market day.

**Hypotheses (not proven root cause)**: Android background sleep, network
interface availability, DNS resolver state, or device power management may
suppress network during unattended cron runs. Termux was already configured as
unrestricted in Android battery settings; disabling battery optimization is
therefore not a confirmed fix. The actual trigger has not been identified.

**Incident status**: OPEN — not resolved until a future unattended 10:00 AM NY
cron run completes with Telegram delivery confirmed in `cron_dividend_bot.log`.

## Cron

Current cron block:
```
# dividend-capture-scanner BEGIN
CRON_TZ=America/New_York
0 10 * * 1-5 cd /data/data/com.termux/files/home/dividend-capture-scanner && /data/data/com.termux/files/usr/bin/bash /data/data/com.termux/files/home/dividend-capture-scanner/run_bot.sh --report --telegram-clean-only --daily-heartbeat --report-dir reports/us_market_$(date +\%Y\%m\%d) >> /data/data/com.termux/files/home/dividend-capture-scanner/cron_dividend_bot.log 2>&1
# dividend-capture-scanner END
```

Meaning: runs Monday–Friday at 10:00 New York time, sends clean-signal alerts,
sends daily heartbeat, writes reports, and appends launcher output to
`cron_dividend_bot.log`.

Verify cron:
```
crontab -l | sed -n "/dividend-capture-scanner BEGIN/,/dividend-capture-scanner END/p" | cat -vet
pgrep -af "crond|cron" || echo "FAIL_NO_CROND_PROCESS"
```

## Termux:Boot

crond is started on boot by `~/.termux/boot/00-termux-services.sh` via
termux-services. The `start-crond` script is an additional safety net.

Verify boot coverage:
```
ls -l ~/.termux/boot/
tail -20 ~/termux_boot_crond.log
tail -20 ~/termux_boot_services.log
```
