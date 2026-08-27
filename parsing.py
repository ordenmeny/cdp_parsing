import json
from collections.abc import Sequence
from urllib.parse import parse_qs, quote, urljoin, urlsplit

from parsek_cdp import Element, ElementState, Page, ProtocolError

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


class MegamarketCardParser:
    """Сбор ссылок на продавцов по карточкам товаров.

    В выдаче есть только имя продавца, ссылка на его магазин — на странице
    карточки, поэтому карточку приходится открывать. Но продавцы в выдаче
    повторяются, поэтому в карточку заходим один раз на продавца, а остальным
    его карточкам проставляем уже найденную ссылку.
    """

    BASE_URL = "https://megamarket.ru"
    BLANK_URL = "about:blank"
    SHOP_PATH = "/shop/"

    MERCHANT_LINK_SELECTOR = ".merchant-header__lable"
    MERCHANT_NAME_SELECTOR = ".pdp-merchant-rating-block__merchant-name"
    MERCHANT_BLOCK_SELECTOR = ".pdp-merchant-rating-block__merchant-name-with-rating"
    POPOVER_LINK_SELECTOR = ".pdp-merchant-rating-block__popover a[href]"

    # Тычок по элементу без координат: часть обработчиков висит на клике,
    # часть на наведении, поэтому шлём и то и другое.
    JS_POKE = """
function () {
    var node = this;
    ["pointerover", "mouseover", "pointerenter", "mouseenter",
     "pointermove", "mousemove", "pointerdown", "mousedown",
     "pointerup", "mouseup", "click"].forEach(function (type) {
        node.dispatchEvent(new MouseEvent(type, {
            bubbles: true, cancelable: true, view: window,
        }));
    });
}
"""

    # Обход состояния страницы: у продавца ищем поле со ссылкой на магазин.
    # Предложений на карточке может быть несколько, поэтому сверяем продавца
    # по id из ссылки, а имя — только как запасной признак.
    JS_SHOP_LINK = """
(function (merchantId, merchantName) {
    var state = window.__APP__;
    if (!state || typeof state !== "object") { return ""; }
    var seen = new Set();
    var stack = [state];
    var byName = "";
    while (stack.length) {
        var node = stack.pop();
        if (!node || typeof node !== "object" || seen.has(node)) { continue; }
        seen.add(node);
        var url = node.url || node.merchantUrl || node.slug || "";
        if (typeof url === "string" && url.indexOf("/shop/") !== -1) {
            if (merchantId && String(node.id || node.merchantId || "") === merchantId) {
                return url;
            }
            if (!byName && merchantName
                    && String(node.name || node.merchantName || "") === merchantName) {
                byName = url;
            }
        }
        for (var key in node) {
            if (node[key] && typeof node[key] === "object") { stack.push(node[key]); }
        }
    }
    return byName;
})(%s, %s)
"""

    def __init__(
            self,
            page: Page,
            *,
            number_visits: int | None = None,
            captcha_timeout: float = 300,
            popover_timeout: float = 10,
    ) -> None:
        self.page = page
        self.number_visits = number_visits
        self.captcha_timeout = captcha_timeout
        self.popover_timeout = popover_timeout
        self._seller_links: dict[str, str] = {}
        self._visits = 0

    @property
    def _page_ready_selector(self) -> str:
        return f"{self.MERCHANT_LINK_SELECTOR}, {self.MERCHANT_NAME_SELECTOR}"

    @staticmethod
    def _merchant_id(card_link: str) -> str:
        """Id продавца из ссылки на карточку: параметр адреса или хвост slug."""
        parts = urlsplit(card_link)
        params = parse_qs(parts.query) | parse_qs(parts.fragment.lstrip("#?"))
        found = (
                params.get("merchantId")
                or params.get("exclusiveMerchantId")
                or [parts.path.strip("/").rpartition("_")[2]]
        )
        return found[0] if found[0].isdigit() else ""

    @classmethod
    def _seller_key(cls, card: CardToPars) -> str:
        """Продавца различаем по id из ссылки, а если его нет — по имени."""
        return cls._merchant_id(card.card_link) or normalize_text(card.seller).casefold()

    @classmethod
    def _normalize_shop_link(cls, href: str) -> str:
        """Оставить от ссылки только корень магазина, чужие ссылки отбросить."""
        if not href:
            return ""
        path = urlsplit(urljoin(cls.BASE_URL, href)).path
        if not path.startswith(cls.SHOP_PATH):
            return ""
        slug = path[len(cls.SHOP_PATH):].strip("/").split("/")[0]
        return f"{cls.BASE_URL}{cls.SHOP_PATH}{slug}/" if slug else ""

    async def _first_shop_link(self, selector: str) -> str:
        for element in await self.page.select_all(selector):
            shop_link = self._normalize_shop_link(element.attributes.get("href", ""))
            if shop_link:
                return shop_link
        return ""

    async def _popover_is_open(self) -> bool:
        return await self.page.select(selector=self.POPOVER_LINK_SELECTOR) is not None

    async def _open_seller_popover(self) -> bool:
        """Раскрыть окно продавца.

        Сначала тычок из JS по имени, потом по всему блоку с именем, и только
        потом настоящий клик мышью: его координаты берутся из box model, и на
        прокрученной странице он может промахнуться мимо элемента.
        """
        attempts = (
            (self.MERCHANT_NAME_SELECTOR, False),
            (self.MERCHANT_BLOCK_SELECTOR, False),
            (self.MERCHANT_NAME_SELECTOR, True),
        )
        for selector, by_mouse in attempts:
            # окно могло раскрыться от предыдущей попытки — второй тычок его закроет
            if await self._popover_is_open():
                return True
            element = await self.page.select(selector=selector)
            if element is None:
                continue
            try:
                if by_mouse:
                    await element.mouse_click()
                else:
                    await element.apply(self.JS_POKE)
                await self.page.wait_for_selector(
                    self.POPOVER_LINK_SELECTOR,
                    state=ElementState.ATTACHED,
                    timeout=self.popover_timeout,
                )
                return True
            except (TimeoutError, ProtocolError):
                continue
        return await self._popover_is_open()

    async def _shop_link_from_state(self, card: CardToPars) -> str:
        """Ссылка на магазин лежит в состоянии страницы — это дешевле клика."""
        expression = self.JS_SHOP_LINK % (
            json.dumps(self._merchant_id(card.card_link)),
            json.dumps(normalize_text(card.seller)),
        )
        try:
            found = await self.page.evaluate(expression)
        except ProtocolError:
            return ""
        return self._normalize_shop_link(found if isinstance(found, str) else "")

    async def _shop_link_from_popover(self) -> str:
        """На обычной карточке ссылка появляется только после клика по продавцу."""
        if await self.page.select(selector=self.MERCHANT_NAME_SELECTOR) is None:
            print("   блок продавца на странице не найден")
            return ""
        if not await self._open_seller_popover():
            print("   окно продавца не раскрылось")
            return ""
        return await self._first_shop_link(self.POPOVER_LINK_SELECTOR)

    async def _parse_seller_link(self, card: CardToPars) -> str:
        print(f"Открываем карточку продавца «{card.seller}»: {card.card_link}")

        # Соседние карточки могут отличаться только хешем — тогда переход не
        # перезагружает страницу. Через пустую страницу document всегда новый.
        await self.page.navigate(self.BLANK_URL)
        await self.page.navigate(card.card_link)

        try:
            await self.page.wait_for_selector(
                self._page_ready_selector,
                state=ElementState.ATTACHED,
                timeout=self.captcha_timeout,
            )
        except TimeoutError:
            print(f"Карточка не открылась: {card.card_link}")
            return ""

        async with self.page.domain_enabled(self.page.cdp.DOM):
            # в витрине продавца ссылка лежит прямо в шапке, кликать нечего
            shop_link = await self._first_shop_link(self.MERCHANT_LINK_SELECTOR)
            print(f"   шапка витрины: {shop_link or 'нет'}")

            if not shop_link:
                # обычная карточка: клик по продавцу -> окно -> ссылка
                shop_link = await self._shop_link_from_popover()
                print(f"   окно продавца: {shop_link or 'нет'}")

            if not shop_link:
                # запасной путь, если окно так и не раскрылось
                shop_link = await self._shop_link_from_state(card)
                print(f"   состояние страницы: {shop_link or 'нет'}")

        if not shop_link:
            print(f"Ссылку на магазин продавца «{card.seller}» не нашли")
        return shop_link

    def _visits_left(self) -> bool:
        return self.number_visits is None or self._visits < self.number_visits

    async def parse(self, cards: Sequence[CardToPars]) -> list[CardToPars]:
        print(f"Собираем ссылки на продавцов, карточек: {len(cards)}")

        for card in cards:
            key = self._seller_key(card)
            if key in self._seller_links:
                card.seller_link = self._seller_links[key]
                continue

            if not self._visits_left():
                print(
                    f"Открыто карточек: {self._visits} — это лимит, "
                    f"к продавцу «{card.seller}» не заходим"
                )
                continue

            self._visits += 1
            shop_link = await self._parse_seller_link(card)
            self._seller_links[key] = shop_link
            card.seller_link = shop_link

        print(
            f"Продавцов найдено: {len(self._seller_links)}, "
            f"открыто карточек: {self._visits}"
        )
        return list(cards)
