import asyncio

from parsek_cdp import Browser

import utils
from config import settings
from domain import CardToPars
from parsing import MegamarketParsePage
from report import ExcelReport
from utils import print_cards


async def connect_browser(endpoint: str) -> Browser:
    return await Browser.connect_http(endpoint)


async def main() -> None:
    browser = await connect_browser(settings.browser_endpoint)
    try:
        page = await browser.new_page()

        parser = MegamarketParsePage(page)
        query = utils.read_query()
        cards = await parser.parse(query)

        print_cards(cards)
        ExcelReport(cards, model=CardToPars, query=query).save()
    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
