#!/usr/bin/env python3
"""Truthful Telegram delivery with structured, credential-safe audit logs."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable

TELEGRAM_LOG_PREFIX = "TELEGRAM_DELIVERY "


@dataclass(frozen=True)
class TelegramDeliveryResult:
    kind: str
    subject: str
    required: bool
    attempted: bool
    delivered: bool
    outcome: str
    status_code: int | None = None
    detail: str = ""


def _sanitize(value: Any, token: str = "") -> str:
    text = str(value or "")
    if token:
        text = text.replace(token, "[REDACTED]")
    text = re.sub(r"/bot[^/\s]+/", "/bot[REDACTED]/", text)
    return " ".join(text.split())[:300]


def _log_result(logger: logging.Logger, result: TelegramDeliveryResult) -> None:
    payload = json.dumps(asdict(result), sort_keys=True, ensure_ascii=True)
    level = logging.INFO if result.delivered or not result.required else logging.ERROR
    logger.log(level, "%s%s", TELEGRAM_LOG_PREFIX, payload)


def send_telegram(
    token: str,
    chat_id: str,
    text: str,
    logger: logging.Logger,
    *,
    kind: str,
    subject: str = "",
    required: bool = True,
    post: Callable[..., Any] | None = None,
) -> TelegramDeliveryResult:
    """Send one Telegram message and return the verified API outcome.

    HTTP 200 alone is insufficient: Telegram's JSON body must also contain
    ``{"ok": true}``. Credentials and message content are never logged.
    The requests dependency is loaded only for a real send so offline tests can
    import and exercise this module without installing runtime dependencies.
    """
    if not token or not chat_id:
        result = TelegramDeliveryResult(
            kind=kind,
            subject=subject,
            required=required,
            attempted=False,
            delivered=False,
            outcome="missing_credentials",
        )
        _log_result(logger, result)
        return result

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        if post is None:
            import requests

            post = requests.post

        response = post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        status_code = int(getattr(response, "status_code", 0) or 0)
        try:
            body = response.json()
        except Exception:
            body = None

        api_ok = isinstance(body, dict) and body.get("ok") is True
        if status_code == 200 and api_ok:
            result = TelegramDeliveryResult(
                kind=kind,
                subject=subject,
                required=required,
                attempted=True,
                delivered=True,
                outcome="delivered",
                status_code=status_code,
            )
        else:
            description = body.get("description") if isinstance(body, dict) else ""
            result = TelegramDeliveryResult(
                kind=kind,
                subject=subject,
                required=required,
                attempted=True,
                delivered=False,
                outcome="api_rejected" if body is not None else "invalid_response",
                status_code=status_code,
                detail=_sanitize(description or getattr(response, "text", ""), token),
            )
    except Exception as exc:
        result = TelegramDeliveryResult(
            kind=kind,
            subject=subject,
            required=required,
            attempted=True,
            delivered=False,
            outcome="transport_error",
            detail=_sanitize(exc, token),
        )

    _log_result(logger, result)
    return result
