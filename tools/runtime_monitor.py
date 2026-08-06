#!/usr/bin/env python3
"""Publish compact DQP runtime status to a private, unguessable ntfy topic.

The publisher is optional and non-blocking.  It exposes no credentials, market
positions, or Telegram content.  A remote monitor can distinguish a successful
run, a failed run, and a completely missing run by polling the topic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

NTFY_BASE_URL = "https://ntfy.sh"
TOPIC_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


@dataclass(frozen=True)
class MonitorPublishResult:
    configured: bool
    attempted: bool
    delivered: bool
    outcome: str
    status_code: int | None = None
    detail: str = ""


RequestPost = Callable[..., Any]


def _sanitize(value: Any, topic: str = "") -> str:
    text = str(value or "")
    if topic:
        text = text.replace(topic, "[REDACTED_TOPIC]")
    return " ".join(text.split())[:240]


def publish_runtime_event(
    topic: str,
    event: str,
    payload: dict[str, Any],
    *,
    request_post: RequestPost | None = None,
    timeout_seconds: int = 15,
) -> MonitorPublishResult:
    topic = str(topic or "").strip()
    if not topic:
        return MonitorPublishResult(
            configured=False,
            attempted=False,
            delivered=False,
            outcome="disabled",
        )
    if TOPIC_PATTERN.fullmatch(topic) is None:
        return MonitorPublishResult(
            configured=True,
            attempted=False,
            delivered=False,
            outcome="invalid_topic",
            detail="topic must be 20-128 letters, numbers, underscores, or hyphens",
        )

    if request_post is None:
        import requests

        request_post = requests.post

    message = {
        "schema_version": 1,
        "event": event,
        **payload,
    }
    success = bool(payload.get("success"))
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Title": "DQP Runtime",
        "Tags": "white_check_mark" if success else "warning",
        "Priority": "3" if success else "5",
    }

    try:
        response = request_post(
            f"{NTFY_BASE_URL}/{topic}",
            data=json.dumps(message, sort_keys=True, separators=(",", ":")),
            headers=headers,
            timeout=max(1, int(timeout_seconds)),
        )
        status = int(getattr(response, "status_code", 0) or 0)
        try:
            body = response.json()
        except Exception:
            body = None
        delivered = bool(status == 200 and isinstance(body, dict) and body.get("id"))
        return MonitorPublishResult(
            configured=True,
            attempted=True,
            delivered=delivered,
            outcome="delivered" if delivered else "rejected",
            status_code=status,
            detail="" if delivered else _sanitize(getattr(response, "text", ""), topic),
        )
    except Exception as exc:
        return MonitorPublishResult(
            configured=True,
            attempted=True,
            delivered=False,
            outcome="transport_error",
            detail=_sanitize(f"{type(exc).__name__}: {exc}", topic),
        )
