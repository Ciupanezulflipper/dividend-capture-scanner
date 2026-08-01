#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import logging
import unittest

from telegram_delivery import TELEGRAM_LOG_PREFIX, send_telegram


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class TelegramDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stream = io.StringIO()
        self.logger = logging.getLogger(f"telegram-test-{id(self)}")
        self.logger.handlers.clear()
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        self.logger.addHandler(handler)
        self.logger.propagate = False

    def _payload(self) -> dict:
        line = self.stream.getvalue().strip().split(TELEGRAM_LOG_PREFIX, 1)[1]
        return json.loads(line)

    def test_http_200_and_ok_true_is_delivered(self) -> None:
        result = send_telegram(
            "secret-token",
            "123",
            "message",
            self.logger,
            kind="heartbeat",
            post=lambda *args, **kwargs: FakeResponse(200, {"ok": True}),
        )
        self.assertTrue(result.delivered)
        self.assertEqual(result.outcome, "delivered")
        payload = self._payload()
        self.assertTrue(payload["delivered"])
        self.assertNotIn("secret-token", self.stream.getvalue())
        self.assertNotIn("message", self.stream.getvalue())

    def test_http_200_with_ok_false_is_failure(self) -> None:
        result = send_telegram(
            "secret-token",
            "123",
            "message",
            self.logger,
            kind="signal",
            subject="PNW",
            post=lambda *args, **kwargs: FakeResponse(
                200, {"ok": False, "description": "chat not found"}
            ),
        )
        self.assertFalse(result.delivered)
        self.assertEqual(result.outcome, "api_rejected")
        self.assertEqual(result.status_code, 200)
        self.assertIn("ERROR", self.stream.getvalue())

    def test_missing_credentials_is_not_attempted(self) -> None:
        result = send_telegram(
            "",
            "",
            "message",
            self.logger,
            kind="admin_warning",
            subject="DATA_PROVIDER_FAILURE",
        )
        self.assertFalse(result.attempted)
        self.assertFalse(result.delivered)
        self.assertEqual(result.outcome, "missing_credentials")

    def test_transport_error_redacts_token(self) -> None:
        token = "very-secret-token"

        def fail(*args, **kwargs):
            raise RuntimeError(
                f"HTTPSConnectionPool(host='api.telegram.org', url='/bot{token}/sendMessage')"
            )

        result = send_telegram(
            token,
            "123",
            "message",
            self.logger,
            kind="heartbeat",
            post=fail,
        )
        self.assertFalse(result.delivered)
        self.assertEqual(result.outcome, "transport_error")
        self.assertNotIn(token, self.stream.getvalue())
        self.assertIn("[REDACTED]", self.stream.getvalue())

    def test_invalid_json_response_is_not_success(self) -> None:
        result = send_telegram(
            "token",
            "123",
            "message",
            self.logger,
            kind="heartbeat",
            post=lambda *args, **kwargs: FakeResponse(
                200, ValueError("not json"), "not json"
            ),
        )
        self.assertFalse(result.delivered)
        self.assertEqual(result.outcome, "invalid_response")


if __name__ == "__main__":
    unittest.main()
