import asyncio
from dataclasses import dataclass
from pathlib import Path

from parsek_cdp import Browser, ProtocolError
from parsek_cdp.core.target import Target
from websockets.exceptions import ConnectionClosed

from megamarket.cdp.cdp_metrics import collect_cdp_metrics
from megamarket.cdp.browser_endpoint import connect_browser
from megamarket.cdp.parsek_compat import install_parsek_target_race_fix
from megamarket.config import settings
from megamarket.domain import CardToPars
from megamarket.parsers.scrolling import MegamarketScrollPage
from megamarket.storage.report import ExcelReport
from megamarket.utils import ScrollCommand, parse_input_command


@dataclass(frozen=True, slots=True)
class ParseResult:
    query: str
    cards_count: int
    output_path: Path


class ParserBrowserUnavailable(RuntimeError):
    pass


class InvalidParseCommand(ValueError):
    pass


class ParserService:
    async def parse(self, command_value: str) -> ParseResult:
        try:
            command = parse_input_command(command_value)
        except ValueError as error:
            raise InvalidParseCommand(str(error)) from error
        if not isinstance(command, ScrollCommand):
            raise InvalidParseCommand(
                "Ожидается команда формата scrolling||<запрос>"
            )

        browser = await self._connect_browser()
        page = None
        parser = None
        try:
            page = await browser.new_page()
            with collect_cdp_metrics(settings.cdp_metrics) as metrics:
                parser = MegamarketScrollPage(
                    page,
                    in_stock_only=True,
                    cdp_metrics=metrics,
                )
                cards = await parser.parse(command.query)

            output_path = ExcelReport(
                cards,
                model=CardToPars,
                query=command.query,
            ).save()
            return ParseResult(
                query=command.query,
                cards_count=len(cards),
                output_path=output_path,
            )
        finally:
            if page is not None and (parser is None or not parser.interrupted):
                try:
                    await asyncio.wait_for(page.cdp.Page.close(), timeout=2)
                except (
                        TimeoutError,
                        ConnectionError,
                        ConnectionClosed,
                        ProtocolError,
                ):
                    pass
            try:
                await Target.close(browser)
            except (ConnectionError, ConnectionClosed, ProtocolError):
                pass

    @staticmethod
    async def _connect_browser() -> Browser:
        install_parsek_target_race_fix()
        try:
            return await asyncio.wait_for(
                connect_browser(settings.browser_endpoint),
                timeout=30,
            )
        except Exception as error:
            raise ParserBrowserUnavailable(
                f"Не удалось подключиться к браузеру: {settings.browser_endpoint}"
            ) from error
