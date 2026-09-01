import asyncio

from parsek_cdp import Browser, ProtocolError
from websockets.exceptions import ConnectionClosed

import utils
from config import settings
from domain import CardToPars, Stock
from parsing import (
    MegamarketParseCard,
    MegamarketParsePage,
)
from report import ExcelReport
from utils import print_cards


async def connect_browser(endpoint: str) -> Browser:
    return await Browser.connect_http(endpoint)


async def main() -> None:
    browser = await connect_browser(settings.browser_endpoint)
    try:
        query = utils.read_query()

        page = await browser.new_page()
        try:
            in_stock_parser = MegamarketParsePage(
                page,
                in_stock_only=True,
            )
            in_stock_cards = await in_stock_parser.parse(query)
        finally:
            try:
                await page.cdp.Page.close()
            except (ConnectionError, ConnectionClosed, ProtocolError):
                # Вкладка могла быть закрыта вручную.
                pass

        # Определение наличия по второму проходу пока отключено: отсутствие
        # карточки в фильтрованной выдаче не гарантирует отсутствие товара.
        # page = await browser.new_page()
        # in_stock_parser = MegamarketParsePage(page, in_stock_only=True)
        # in_stock_cards = await in_stock_parser.parse(query)
        #
        # in_stock_links = {
        #     utils.normalize_link(card.card_link)
        #     for card in in_stock_cards
        # }
        # for card in all_stock_cards:
        #     card.stock = (
        #         Stock.IN_STOCK
        #         if utils.normalize_link(card.card_link) in in_stock_links
        #         else Stock.OUT_OF_STOCK
        #     )

        report = ExcelReport(in_stock_cards, model=CardToPars, query=query)
        output_path = report.save()

        if not in_stock_parser.interrupted:
            try:
                await MegamarketParseCard(browser, in_stock_cards).parse_all()
            finally:
                # При сбое сохраняем также ссылки, собранные до него.
                report.save(output_path)

        # print_cards(in_stock_cards)

    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
