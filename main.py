import asyncio
from dataclasses import dataclass
from urllib.parse import quote

from parsek_cdp import Browser, ElementState, Page
from utils import normalize_text, print_cards, read_query

BROWSER_PORT: int = 51111
CAPTCHA_TIMEOUT_SECONDS = 300
CARD_SELECTOR = '[data-test="product-item"][data-list-id="main"]'
TITLE_SELECTOR = '[data-test="product-name-link"]'
PRICE_SELECTOR = '[data-test="product-price"]'
SELLER_SELECTOR = '[data-test="merchant-name"]'
NOT_FOUND_SELECTOR = ".listing-not-found-block"
PAGE_READY_SELECTOR = f"{CARD_SELECTOR}, {NOT_FOUND_SELECTOR}"


@dataclass
class CardToPars:
    title: str
    price: str
    seller: str


async def connect_browser(port: int) -> Browser:
    return await Browser.connect_http(f"http://127.0.0.1:{port}")


def build_catalog_url(query: str, page_number: int) -> str:
    if page_number < 1:
        raise ValueError("Номер страницы должен быть больше нуля")

    path = "/catalog/" if page_number == 1 else f"/catalog/page-{page_number}/"
    return f"https://megamarket.ru{path}?q={quote(query)}"


async def parse_cards(page: Page) -> list[CardToPars]:
    print("Начинаем парсить...")

    await page.wait_for_selector(
        CARD_SELECTOR,
        state=ElementState.ATTACHED,
        timeout=CAPTCHA_TIMEOUT_SECONDS,
    )

    raw_cards = await page.evaluate(
        f"""
        Array.from(document.querySelectorAll({CARD_SELECTOR!r})).map(card => ({{
            title: card.querySelector({TITLE_SELECTOR!r})?.textContent ?? '',
            price: card.querySelector({PRICE_SELECTOR!r})?.textContent ?? '',
            seller: card.querySelector({SELLER_SELECTOR!r})?.textContent ?? '',
        }}))
        """
    )

    cards = []
    for raw_card in raw_cards or []:
        card = CardToPars(
            title=normalize_text(raw_card.get("title", "")),
            price=normalize_text(raw_card.get("price", "")),
            seller=normalize_text(raw_card.get("seller", "")),
        )
        if card.title and card.price and card.seller:
            cards.append(card)

    return cards


async def is_not_found_page(page: Page) -> bool:
    await page.wait_for_selector(
        PAGE_READY_SELECTOR,
        state=ElementState.ATTACHED,
        timeout=CAPTCHA_TIMEOUT_SECONDS,
    )
    return bool(
        await page.evaluate(
            f"Boolean(document.querySelector({NOT_FOUND_SELECTOR!r}))"
        )
    )


async def main() -> None:
    browser = await connect_browser(BROWSER_PORT)
    try:
        page = await browser.new_page()
        query = read_query()
        number_pages: int | None = 3
        number_items: int | None = 2

        all_cards: list[CardToPars] = []
        page_number = 1

        while number_pages is None or page_number <= number_pages:
            url = build_catalog_url(query, page_number)
            print(f"Переходим на страницу {page_number}: {url}")
            await page.navigate(url, wait_load=True)

            if await is_not_found_page(page):
                print(f"Страница {page_number} не содержит результатов. Останавливаемся.")
                break

            page_cards = await parse_cards(page)
            if number_items is not None:
                page_cards = page_cards[:number_items]

            print(f"На странице {page_number} собрано карточек: {len(page_cards)}")
            all_cards.extend(page_cards)

            if number_pages is not None and page_number >= number_pages:
                break

            page_number += 1

        print_cards(all_cards)
    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
