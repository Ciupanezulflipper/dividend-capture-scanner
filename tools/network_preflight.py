#!/usr/bin/env python3
"""Bounded network preflight for scheduled DQP production scans.

The scanner depends on Yahoo Finance for market data and Telegram for required
operational delivery.  A scheduled run should not spend ten minutes processing
503 guaranteed failures when DNS or TLS is already broken.

This module performs small read-only probes, retries for a bounded window, and
returns structured evidence.  It never sends a Telegram message and never
changes scanner history.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Sequence

YAHOO_PROBE_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "AAPL?range=5d&interval=1d"
)
WIKIPEDIA_PROBE_URL = (
    "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
)


@dataclass(frozen=True)
class ProbeResult:
    name: str
    critical: bool
    ok: bool
    status_code: int | None
    detail: str


@dataclass(frozen=True)
class PreflightResult:
    attempted: bool
    passed: bool
    attempts: int
    max_attempts: int
    waited_seconds: int
    recovered_during_retry: bool
    results: tuple[ProbeResult, ...]


RequestGet = Callable[..., Any]
Sleep = Callable[[float], None]
AttemptCallback = Callable[[int, int, Sequence[ProbeResult]], None]


def _sanitize(value: Any, token: str = "") -> str:
    text = str(value or "")
    if token:
        text = text.replace(token, "[REDACTED]")
    text = re.sub(r"/bot[^/\s]+/", "/bot[REDACTED]/", text)
    return " ".join(text.split())[:240]


def _json_body(response: Any) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _probe(
    *,
    name: str,
    critical: bool,
    url: str,
    validator: Callable[[Any, dict[str, Any] | None], tuple[bool, str]],
    request_get: RequestGet,
    timeout_seconds: int,
    token: str = "",
) -> ProbeResult:
    try:
        response = request_get(
            url,
            headers={"User-Agent": "DQP-Network-Preflight/1.0"},
            timeout=timeout_seconds,
        )
        status = int(getattr(response, "status_code", 0) or 0)
        payload = _json_body(response)
        ok, detail = validator(response, payload)
        return ProbeResult(
            name=name,
            critical=critical,
            ok=bool(status == 200 and ok),
            status_code=status,
            detail=_sanitize(detail, token),
        )
    except Exception as exc:
        return ProbeResult(
            name=name,
            critical=critical,
            ok=False,
            status_code=None,
            detail=_sanitize(f"{type(exc).__name__}: {exc}", token),
        )


def probe_once(
    token: str,
    *,
    require_telegram: bool = True,
    request_get: RequestGet | None = None,
    timeout_seconds: int = 15,
) -> tuple[ProbeResult, ...]:
    if request_get is None:
        import requests

        request_get = requests.get

    def yahoo_validator(
        _response: Any, payload: dict[str, Any] | None
    ) -> tuple[bool, str]:
        chart = payload.get("chart") if payload else None
        result = chart.get("result") if isinstance(chart, dict) else None
        good = isinstance(result, list) and bool(result)
        return good, "chart data available" if good else "missing chart result"

    def telegram_validator(
        _response: Any, payload: dict[str, Any] | None
    ) -> tuple[bool, str]:
        good = bool(payload and payload.get("ok") is True)
        return good, "getMe ok" if good else "Telegram API did not return ok=true"

    def wikipedia_validator(
        response: Any, _payload: dict[str, Any] | None
    ) -> tuple[bool, str]:
        content = getattr(response, "content", b"") or b""
        good = len(content) >= 1_000
        return good, f"content_bytes={len(content)}"

    results = [
        _probe(
            name="yahoo_chart",
            critical=True,
            url=YAHOO_PROBE_URL,
            validator=yahoo_validator,
            request_get=request_get,
            timeout_seconds=timeout_seconds,
        )
    ]

    if require_telegram and not token:
        results.append(
            ProbeResult(
                name="telegram_getme",
                critical=True,
                ok=False,
                status_code=None,
                detail="missing Telegram token",
            )
        )
    elif require_telegram:
        results.append(
            _probe(
                name="telegram_getme",
                critical=True,
                url=f"https://api.telegram.org/bot{token}/getMe",
                validator=telegram_validator,
                request_get=request_get,
                timeout_seconds=timeout_seconds,
                token=token,
            )
        )

    results.append(
        _probe(
            name="wikipedia_sp500",
            critical=False,
            url=WIKIPEDIA_PROBE_URL,
            validator=wikipedia_validator,
            request_get=request_get,
            timeout_seconds=timeout_seconds,
        )
    )
    return tuple(results)


def _attempt_count(max_wait_seconds: int, interval_seconds: int) -> int:
    if max_wait_seconds <= 0 or interval_seconds <= 0:
        return 1
    return max_wait_seconds // interval_seconds + 1


def run_preflight(
    token: str,
    *,
    require_telegram: bool = True,
    max_wait_seconds: int = 1_800,
    interval_seconds: int = 300,
    timeout_seconds: int = 15,
    request_get: RequestGet | None = None,
    sleep: Sleep = time.sleep,
    on_attempt: AttemptCallback | None = None,
) -> PreflightResult:
    max_wait_seconds = max(0, int(max_wait_seconds))
    interval_seconds = max(0, int(interval_seconds))
    timeout_seconds = max(1, int(timeout_seconds))
    max_attempts = _attempt_count(max_wait_seconds, interval_seconds)

    # Missing credentials cannot recover through network retries.
    if require_telegram and not token:
        max_attempts = 1

    final_results: tuple[ProbeResult, ...] = ()
    for attempt in range(1, max_attempts + 1):
        final_results = probe_once(
            token,
            require_telegram=require_telegram,
            request_get=request_get,
            timeout_seconds=timeout_seconds,
        )
        if on_attempt is not None:
            on_attempt(attempt, max_attempts, final_results)

        passed = all(item.ok for item in final_results if item.critical)
        if passed:
            return PreflightResult(
                attempted=True,
                passed=True,
                attempts=attempt,
                max_attempts=max_attempts,
                waited_seconds=(attempt - 1) * interval_seconds,
                recovered_during_retry=attempt > 1,
                results=final_results,
            )

        if attempt < max_attempts:
            sleep(interval_seconds)

    return PreflightResult(
        attempted=True,
        passed=False,
        attempts=max_attempts,
        max_attempts=max_attempts,
        waited_seconds=max(0, (max_attempts - 1) * interval_seconds),
        recovered_during_retry=False,
        results=final_results,
    )
