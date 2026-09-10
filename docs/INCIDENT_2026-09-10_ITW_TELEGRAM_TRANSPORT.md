# Incident — ITW Clean Signal Lost on Transient Telegram Transport Failure

Date: 2026-09-10
Status: RESOLVED
Severity: Reliability / missed notification

## Problem

The 2026-09-10 DQP run generated one clean signal, ITW, but the user did not receive the Telegram signal notification.

## Impact

One qualifying clean signal was not delivered. The daily heartbeat was still delivered, so a heartbeat alone did not prove that every required signal notification succeeded.

## Evidence

Run health recorded:

- `scanner_exit_code=23`
- `telegram_delivery_not_verified`
- `delivery_required=true`
- `delivery_verified=false`
- `signal_attempt_count=1`
- `signal_failure_count=1`
- `signal_success_count=0`
- heartbeat claimed and delivered

Scanner log recorded ITW as a generated HIGH-priority clean candidate and then:

`TELEGRAM_DELIVERY ... kind=signal ... delivered=false ... outcome=transport_error ... subject=ITW`

The transport detail was a connection reset by peer. Roughly five seconds later the heartbeat was delivered successfully with Telegram HTTP 200.

No ITW row existed in `history.json`, which is correct because history commits only after verified delivery.

## Root cause

The delivery layer performed only one attempt. A transient connection reset therefore caused a valid clean signal to be lost even though Telegram connectivity recovered seconds later.

This was not deduplication, not strategy rejection, and not a history corruption problem.

## Correction

Implemented bounded retry in `telegram_delivery.py` for **required signal** messages when and only when the failure is a transient `transport_error`.

Behavior:

- initial attempt;
- up to two bounded retries after short delays;
- stop immediately on verified success;
- no retry for Telegram API rejection;
- non-signal messages keep existing single-attempt behavior;
- history remains committed only after verified signal delivery.

Implementation commits:

- `cfb2a2b77062c2da421e0ee53448539545a4678c`
- `140f1b7905dcc8dadfaf190c03c1d7dc24470799`

## Validation

Termux runtime fast-forwarded to `140f1b7`.

`python -m unittest tests.test_telegram_delivery -v`

Result: **8 tests passed**.

Tests include:

- required signal transient failure then recovery;
- required signal exhausting two retries;
- non-signal transport failure not retried;
- API rejection remains failure;
- credential handling and token redaction.

## Prevention rule

A required clean signal must not be considered delivered unless Telegram delivery is positively verified. Transient transport failures may receive bounded retries; history must never be advanced for an unverified delivery.

## Follow-up

No broader messaging redesign is justified by this incident. Monitor the next 3–5 trading days. Keep ITW classified as `QUALIFIED_BUT_DELIVERY_FAILED`; do not retroactively insert it into delivered history.
