"""Измерить CDP-нагрузку парсера на локальной странице с карточками."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from base_parser import PageState  # noqa: E402
from cdp_metrics import collect_cdp_metrics  # noqa: E402
from config import settings  # noqa: E402
from main import connect_browser  # noqa: E402
from parsing import MegamarketParsePage  # noqa: E402


def build_fixture(card_count: int) -> bytes:
    cards = "".join(
        f"""
        <article data-test="product-item" data-list-id="main">
          <a data-test="product-name-link" href="/catalog/product-{number}/">
            Товар {number}
          </a>
          <span data-test="product-price">{number} 000 ₽</span>
          <span data-test="merchant-name">Продавец {number}</span>
          <meta itemprop="image" content="https://images.test/{number}.jpg">
        </article>
        """
        for number in range(1, card_count + 1)
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Fixture</title>"
        f"</head><body><main>{cards}</main></body></html>"
    ).encode("utf-8")


def start_fixture_server(content: bytes) -> tuple[ThreadingHTTPServer, str]:
    class FixtureHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/"


async def measure(endpoint: str, card_count: int) -> bool:
    server, fixture_url = start_fixture_server(build_fixture(card_count))
    browser = None
    page = None
    try:
        browser = await connect_browser(endpoint)
        page = await browser.new_page()
        await page.navigate(fixture_url, wait_load=True, timeout=30)

        parser = MegamarketParsePage(
            page,
            number_pages=1,
            in_stock_only=False,
            cards_poll_interval=0.5,
            cards_stable_checks=3,
        )
        with collect_cdp_metrics(
                True,
                total_label="локальная страница целиком",
        ) as metrics:
            assert metrics is not None
            parser.cdp_metrics = metrics

            state = await parser.wait_page_state()
            if state is not PageState.READY:
                raise RuntimeError(f"Локальная страница не готова: {state}")

            ready_started = time.perf_counter()
            await parser.wait_content_ready()
            ready_elapsed = time.perf_counter() - ready_started

            parse_started = time.perf_counter()
            cards = await parser._parse_current_page_measured(1)
            parse_elapsed = time.perf_counter() - parse_started

            calls = sum(metrics.calls.values())
            describe_calls = metrics.calls["DOM.describeNode"]
            enable_calls = metrics.calls["DOM.enable"]
            disable_calls = metrics.calls["DOM.disable"]
            response_megabytes = metrics.response_bytes / (1024 * 1024)

        checks = {
            "карточек": len(cards) == card_count,
            "CDP-вызовов ≤ 20": calls <= 20,
            "ответов ≤ 1.5 МБ": response_megabytes <= 1.5,
            "DOM.describeNode == 0": describe_calls == 0,
            "DOM.enable/disable == 0/0": enable_calls == disable_calls == 0,
            "parse_current_page ≤ 1 сек.": parse_elapsed <= 1,
            "wait_content_ready ≤ 2 сек.": ready_elapsed <= 2,
        }
        print(
            f"Карточек: {len(cards)}/{card_count}; "
            f"parse_current_page: {parse_elapsed:.3f} сек.; "
            f"wait_content_ready: {ready_elapsed:.3f} сек."
        )
        for label, passed in checks.items():
            print(f"{'OK' if passed else 'FAIL'}: {label}")
        return all(checks.values())
    finally:
        if page is not None:
            try:
                await asyncio.wait_for(page.cdp.Page.close(), timeout=3)
            except Exception:
                pass
        server.shutdown()
        server.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        default=settings.browser_endpoint,
        help="CDP endpoint уже запущенного браузера",
    )
    parser.add_argument("--cards", type=int, default=720)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    raise SystemExit(
        0 if asyncio.run(measure(arguments.endpoint, arguments.cards)) else 1
    )
