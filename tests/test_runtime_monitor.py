#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest

from tools.runtime_monitor import publish_runtime_event


class Response:
    def __init__(self, payload, *, status: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class RuntimeMonitorTests(unittest.TestCase):
    def test_missing_topic_is_cleanly_disabled(self) -> None:
        result = publish_runtime_event("", "run_success", {"success": True})
        self.assertFalse(result.configured)
        self.assertFalse(result.attempted)
        self.assertEqual(result.outcome, "disabled")

    def test_invalid_topic_is_rejected_without_network(self) -> None:
        called = False

        def post(*_args, **_kwargs):
            nonlocal called
            called = True
            return Response({"id": "unused"})

        result = publish_runtime_event(
            "too short", "run_success", {"success": True}, request_post=post
        )
        self.assertTrue(result.configured)
        self.assertFalse(result.attempted)
        self.assertEqual(result.outcome, "invalid_topic")
        self.assertFalse(called)

    def test_success_publishes_compact_json_without_topic_in_message(self) -> None:
        topic = "dqp-1234567890abcdef1234567890abcdef"
        captured = {}

        def post(url, *, data, headers, timeout):
            captured.update(
                {"url": url, "data": data, "headers": headers, "timeout": timeout}
            )
            return Response({"id": "message-id", "time": 1})

        result = publish_runtime_event(
            topic,
            "run_success",
            {
                "scan_date": "2026-08-06",
                "success": True,
                "failure_reasons": [],
            },
            request_post=post,
        )

        self.assertTrue(result.delivered)
        self.assertEqual(result.outcome, "delivered")
        payload = json.loads(captured["data"])
        self.assertEqual(payload["event"], "run_success")
        self.assertEqual(payload["scan_date"], "2026-08-06")
        self.assertNotIn(topic, captured["data"])
        self.assertEqual(captured["headers"]["Priority"], "3")

    def test_failure_event_uses_high_priority(self) -> None:
        captured = {}

        def post(_url, *, data, headers, timeout):
            captured.update({"data": data, "headers": headers, "timeout": timeout})
            return Response({"id": "message-id"})

        result = publish_runtime_event(
            "dqp-1234567890abcdef1234567890abcdef",
            "run_failure",
            {"success": False, "failure_reasons": ["provider_collapse"]},
            request_post=post,
        )
        self.assertTrue(result.delivered)
        self.assertEqual(captured["headers"]["Priority"], "5")

    def test_transport_error_redacts_topic(self) -> None:
        topic = "dqp-1234567890abcdef1234567890abcdef"

        def post(url, **_kwargs):
            raise OSError(f"failure posting {url}")

        result = publish_runtime_event(
            topic,
            "run_failure",
            {"success": False},
            request_post=post,
        )
        self.assertFalse(result.delivered)
        self.assertEqual(result.outcome, "transport_error")
        self.assertNotIn(topic, result.detail)
        self.assertIn("[REDACTED_TOPIC]", result.detail)


if __name__ == "__main__":
    unittest.main()
