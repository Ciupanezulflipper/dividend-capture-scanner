#!/usr/bin/env python3
from __future__ import annotations

import unittest

from tools.network_preflight import probe_once, run_preflight


class Response:
    def __init__(
        self,
        payload=None,
        *,
        status: int = 200,
        content: bytes = b"x" * 2_000,
        text: str = "",
    ) -> None:
        self._payload = payload
        self.status_code = status
        self.content = content
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class NetworkPreflightTests(unittest.TestCase):
    def test_all_critical_probes_pass_while_wikipedia_is_only_advisory(self) -> None:
        def get(url, **_kwargs):
            if "query1.finance.yahoo.com" in url:
                return Response({"chart": {"result": [{"timestamp": [1]}]}})
            if "api.telegram.org" in url:
                return Response({"ok": True, "result": {"id": 1}})
            return Response(None, content=b"short")

        results = probe_once("secret-token", request_get=get)
        by_name = {item.name: item for item in results}
        self.assertTrue(by_name["yahoo_chart"].ok)
        self.assertTrue(by_name["telegram_getme"].ok)
        self.assertFalse(by_name["wikipedia_sp500"].ok)
        self.assertFalse(by_name["wikipedia_sp500"].critical)
        self.assertTrue(all(item.ok for item in results if item.critical))

    def test_retry_recovers_on_second_attempt_without_real_sleep(self) -> None:
        yahoo_calls = 0
        sleeps = []
        attempts = []

        def get(url, **_kwargs):
            nonlocal yahoo_calls
            if "query1.finance.yahoo.com" in url:
                yahoo_calls += 1
                if yahoo_calls == 1:
                    raise OSError("temporary DNS failure")
                return Response({"chart": {"result": [{"timestamp": [1]}]}})
            if "api.telegram.org" in url:
                return Response({"ok": True})
            return Response(None)

        result = run_preflight(
            "token",
            max_wait_seconds=10,
            interval_seconds=5,
            request_get=get,
            sleep=sleeps.append,
            on_attempt=lambda number, maximum, _results: attempts.append(
                (number, maximum)
            ),
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.max_attempts, 3)
        self.assertEqual(result.waited_seconds, 5)
        self.assertTrue(result.recovered_during_retry)
        self.assertEqual(sleeps, [5])
        self.assertEqual(attempts, [(1, 3), (2, 3)])

    def test_exhausted_window_fails_after_initial_attempt_and_retries(self) -> None:
        sleeps = []

        def get(url, **_kwargs):
            if "api.telegram.org" in url:
                return Response({"ok": True})
            if "wikipedia.org" in url:
                return Response(None)
            raise OSError("DNS unavailable")

        result = run_preflight(
            "token",
            max_wait_seconds=10,
            interval_seconds=5,
            request_get=get,
            sleep=sleeps.append,
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(result.waited_seconds, 10)
        self.assertEqual(sleeps, [5, 5])

    def test_missing_telegram_token_fails_once_without_pointless_waiting(self) -> None:
        sleeps = []

        def get(url, **_kwargs):
            if "query1.finance.yahoo.com" in url:
                return Response({"chart": {"result": [{}]}})
            return Response(None)

        result = run_preflight(
            "",
            max_wait_seconds=1_800,
            interval_seconds=300,
            request_get=get,
            sleep=sleeps.append,
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.max_attempts, 1)
        self.assertEqual(sleeps, [])
        telegram = next(item for item in result.results if item.name == "telegram_getme")
        self.assertIn("missing", telegram.detail)

    def test_transport_detail_redacts_telegram_token(self) -> None:
        token = "super-secret-token"

        def get(url, **_kwargs):
            if "api.telegram.org" in url:
                raise OSError(f"failed at {url}")
            if "query1.finance.yahoo.com" in url:
                return Response({"chart": {"result": [{}]}})
            return Response(None)

        results = probe_once(token, request_get=get)
        telegram = next(item for item in results if item.name == "telegram_getme")
        self.assertNotIn(token, telegram.detail)
        self.assertIn("[REDACTED]", telegram.detail)


if __name__ == "__main__":
    unittest.main()
