from urllib.parse import quote, urljoin

from parsek_cdp import Element, ElementState, Page

from domain import CardToPars
from utils import normalize_text


class MegamarketParser:
    BASE_URL = "https://megamarket.ru"
    CARD_SELECTOR = '[data-test="product-item"][data-list-id="main"]'
    TITLE_SELECTOR = '[data-test="product-name-link"]'
    PRICE_SELECTOR = '[data-test="product-price"]'
    SELLER_SELECTOR = '[data-test="merchant-name"]'
    NOT_FOUND_SELECTOR = ".listing-not-found-block"

    def __init__(
            self,
            page: Page,
            *,
            number_pages: int | None = None,
            number_items: int | None = None,
            captcha_timeout: float = 300,
    ) -> None:
        self.page = page
        self.number_pages = number_pages
        self.number_items = number_items
        self.captcha_timeout = captcha_timeout

    @property
    def _page_ready_selector(self) -> str:
        return f"{self.CARD_SELECTOR}, {self.NOT_FOUND_SELECTOR}"

    @classmethod
    def _build_catalog_url(cls, query: str, page_number: int) -> str:
        path = "/catalog/" if page_number == 1 else f"/catalog/page-{page_number}/"
        return f"{cls.BASE_URL}{path}?q={quote(query)}"

    @staticmethod
    async def _get_text(element: Element, selector: str) -> str:
        child = await element.query_selector(selector)
        if child is None:
            return ""
        text = await child.apply("function () { return this.textContent || ''; }")
        return normalize_text(text or "")

    @staticmethod
    async def _get_attribute(
            element: Element,
            selector: str,
            attribute: str,
    ) -> str:
        child = await element.query_selector(selector)
        if child is None:
            return ""
        return child.attributes.get(attribute, "")

    @classmethod
    async def _get_card_link(cls, card_element: Element) -> str:
        href = await cls._get_attribute(
            card_element,
            cls.TITLE_SELECTOR,
            "href",
        )
        return urljoin(cls.BASE_URL, href) if href else ""

    async def _parse_cards(self) -> list[CardToPars]:
        print("Начинаем парсить...")

        await self.page.wait_for_selector(
            self.CARD_SELECTOR,
            state=ElementState.ATTACHED,
            timeout=self.captcha_timeout,
        )

        cards: list[CardToPars] = []
        async with self.page.domain_enabled(self.page.cdp.DOM):
            selected_cards = await self.page.select_all(self.CARD_SELECTOR)
            if self.number_items is not None:
                selected_cards = selected_cards[: self.number_items]

            for card_element in selected_cards:
                card = CardToPars(
                    title=await self._get_text(card_element, self.TITLE_SELECTOR),
                    price=await self._get_text(card_element, self.PRICE_SELECTOR),
                    seller=await self._get_text(card_element, self.SELLER_SELECTOR),
                    card_link=await self._get_card_link(card_element),
                )
                if card.title and card.price and card.seller and card.card_link:
                    cards.append(card)

        return cards

    async def _is_not_found_page(self) -> bool:
        await self.page.wait_for_selector(
            self._page_ready_selector,
            state=ElementState.ATTACHED,
            timeout=self.captcha_timeout,
        )
        return (
                await self.page.select(selector=self.NOT_FOUND_SELECTOR) is not None
        )

    async def parse(self, query: str) -> list[CardToPars]:
        all_cards: list[CardToPars] = []
        page_number = 1

        while self.number_pages is None or page_number <= self.number_pages:
            url = self._build_catalog_url(query, page_number)
            print(f"Переходим на страницу {page_number}: {url}")
            await self.page.navigate(url)

            if await self._is_not_found_page():
                print(
                    f"Страница {page_number} не содержит результатов. "
                    "Останавливаемся."
                )
                break

            page_cards = await self._parse_cards()
            print(f"На странице {page_number} собрано карточек: {len(page_cards)}")
            all_cards.extend(page_cards)

            if self.number_pages is not None and page_number >= self.number_pages:
                break

            page_number += 1

        return all_cards
