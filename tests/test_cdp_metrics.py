import contextlib
import io
import unittest
from unittest.mock import AsyncMock, patch

from parsek_cdp.core.target import CDPConnection

from megamarket.cdp import cdp_metrics


class CDPMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_collects_calls_and_response_size(self):
        connection = CDPConnection()
        output = io.StringIO()
        original_send = AsyncMock(return_value={"value": "данные"})

        with patch.object(cdp_metrics, "_original_send", original_send):
            with contextlib.redirect_stdout(output):
                with cdp_metrics.collect_cdp_metrics(True) as metrics:
                    self.assertIsNotNone(metrics)
                    await connection.send("Runtime.evaluate", {"expression": "1"})

        self.assertEqual(metrics.calls["Runtime.evaluate"], 1)
        self.assertGreater(metrics.response_bytes, 0)
        self.assertIn("Runtime.evaluate: 1", output.getvalue())

    async def test_disabled_collector_returns_none(self):
        with cdp_metrics.collect_cdp_metrics(False) as metrics:
            self.assertIsNone(metrics)


if __name__ == "__main__":
    unittest.main()
