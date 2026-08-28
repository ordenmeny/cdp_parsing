import asyncio

from parsek_cdp import Browser

from config import settings
from domain import CardToPars
from parsing import MegamarketCardParser, MegamarketParsePage
from report import ExcelReport
from utils import print_cards, read_query


async def connect_browser(endpoint: str) -> Browser:
    return await Browser.connect_http(endpoint)


async def main() -> None:
    browser = await connect_browser(settings.browser_endpoint)
    try:
        page = await browser.new_page()
        query = read_query()
        parser = MegamarketParsePage(page)
        cards = await parser.parse(query)

        # card_parser = MegamarketCardParser(page)
        # cards = await card_parser.parse(cards)

        print_cards(cards)
        ExcelReport(cards, model=CardToPars, query=query).save()
    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
