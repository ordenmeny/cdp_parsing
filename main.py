import asyncio

from parsek_cdp import Browser

from parsing import MegamarketCardParser, MegamarketParser
from utils import print_cards, read_query

BROWSER_PORT: int = 51111


async def connect_browser(port: int) -> Browser:
    return await Browser.connect_http(f"http://127.0.0.1:{port}")


async def main() -> None:
    browser = await connect_browser(BROWSER_PORT)
    try:
        page = await browser.new_page()
        query = read_query()
        number_pages: int | None = 3
        number_items: int | None = 2
        number_visits: int | None = None
        parser = MegamarketParser(
            page,
            number_pages=number_pages,
            number_items=number_items,
        )
        cards = await parser.parse(query)

        card_parser = MegamarketCardParser(page, number_visits=number_visits)
        cards = await card_parser.parse(cards)

        print_cards(cards)
    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
