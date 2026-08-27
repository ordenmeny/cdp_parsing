import asyncio
from dataclasses import dataclass
from time import sleep
from urllib.parse import quote

from parsek_cdp import Browser, Page


CARD_SELECTOR = '[data-test="product-item"][data-list-id="main"]'
TITLE_SELECTOR = '[data-test="product-name-link"]'
PRICE_SELECTOR = '[data-test="product-price"]'
SELLER_SELECTOR = '[data-test="merchant-name"]'
CAPTCHA_TIMEOUT_SECONDS = 300


@dataclass
class CardToPars:
    title: str
    price: str
    seller: str


async def connect_browser(proxy: str | None, port: int) -> Browser:
    return await Browser.connect_http(f"http://127.0.0.1:{port}")


def normalize_text(value: str) -> str:
    return " ".join(value.split())


async def parse_cards(page: Page) -> list[CardToPars]:
    print("Начинаем парсить...")
    sleep(10)

    raw_cards = await page.evaluate(
        f"""
        Array.from(document.querySelectorAll({CARD_SELECTOR!r})).map(card => ({{
            title: card.querySelector({TITLE_SELECTOR!r})?.textContent ?? '',
            price: card.querySelector({PRICE_SELECTOR!r})?.textContent ?? '',
            seller: card.querySelector({SELLER_SELECTOR!r})?.textContent ?? '',
        }}))
        """
    )

    print("Сделали запрос, готовим ответ...")

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


def print_cards(cards: list[CardToPars]) -> None:
    print(f"Собрано карточек: {len(cards)}")
    for number, card in enumerate(cards, start=1):
        print(
            f"{number}. {card.title}\n"
            f"   Цена: {card.price}\n"
            f"   Продавец: {card.seller}"
        )


async def main() -> None:
    browser = await connect_browser(None, 51111)

    error_flag = True

    while error_flag:
        try:
            page = await browser.new_page()

            query = "самсунг"
            await page.navigate(
                f"https://megamarket.ru/catalog/?q={quote(query)}", wait_load=True
            )

            cards = await parse_cards(page)
            print_cards(cards)
            error_flag = False
        except KeyboardInterrupt:
            await browser.close()
        except Exception as e:
            print(e)


if __name__ == "__main__":
    asyncio.run(main())
