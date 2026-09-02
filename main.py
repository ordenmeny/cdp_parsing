import asyncio

from parsek_cdp import Browser, ProtocolError
from websockets.exceptions import ConnectionClosed

import utils
from config import settings
from domain import CardToPars, Stock
from parsek_compat import install_parsek_target_race_fix
from parsing import (
    MegamarketParseCard,
    MegamarketParsePage,
)
from report import ExcelReport, join_excel_reports
from slug import SlugifyCard
from utils import print_cards


async def connect_browser(endpoint: str) -> Browser:
    install_parsek_target_race_fix()
    return await Browser.connect_http(endpoint)


def set_sellers_links(cards: list[CardToPars]) -> None:
    """Сформировать ссылки продавцов из слагифицированных названий."""
    SlugifyCard(cards).set_sellers_slugs()


async def main() -> None:
    command = utils.read_command()
    if isinstance(command, utils.JoinCommand):
        join_excel_reports(command.directory)
        return

    browser = await connect_browser(settings.browser_endpoint)
    try:
        query = command.query

        page = await browser.new_page()
        try:
            in_stock_parser = MegamarketParsePage(
                page,
                in_stock_only=True,
                start_page=command.start_page,
            )
            in_stock_cards = await in_stock_parser.parse(query)
            set_sellers_links(in_stock_cards)
        finally:
            if not in_stock_parser.interrupted:
                try:
                    await asyncio.wait_for(page.cdp.Page.close(), timeout=2)
                except (
                        TimeoutError,
                        ConnectionError,
                        ConnectionClosed,
                        ProtocolError,
                ):
                    pass


        report = ExcelReport(
            in_stock_cards,
            model=CardToPars,
            query=query,
        )
        output_path = report.save()

        # print_cards(in_stock_cards)

    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
