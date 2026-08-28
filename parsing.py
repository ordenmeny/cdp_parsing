import asyncio
import json
from collections.abc import Sequence
from urllib.parse import parse_qs, quote, urljoin, urlsplit, urlunsplit

from parsek_cdp import Element, ElementState, Page, ProtocolError

from base_parser import BasePaginatedParser, PageState
from config import settings
from domain import CardToPars, Stock
from exceptions import SiteBlocked
from utils import normalize_text

# Вместо страницы сайт может отдать заглушку «запросы похожи на автоматические».
# Узнаём её по заголовку: он говорит об этом прямым текстом. Разметку заглушки
# для этого не используем — id ниже нужен только чтобы не ждать её впустую.
BLOCKED_HEADING = "запросы с вашего устройства похожи на автоматические"
BLOCKED_SELECTOR = "#request-id"
BLOCKED_MESSAGE = "Сайт решил, что запросы автоматические."


async def is_blocked_page(page: Page) -> bool:
    """Отдал ли сайт заглушку вместо страницы.

    Заголовок читаем одним ``evaluate``, а не через элемент: между поиском
    элемента и чтением его текста включается и выключается домен DOM, из-за
    чего id узла успевает устареть.
    """
    try:
        heading = await page.evaluate(
            "(document.querySelector('h1') || {}).textContent || ''"
        )
    except ProtocolError:
        return False
    return BLOCKED_HEADING in normalize_text(heading or "").casefold()


class MegamarketParsePage(BasePaginatedParser[CardToPars]):
    CARD_SELECTOR = '[data-test="product-item"][data-list-id="main"]'
    TITLE_SELECTOR = '[data-test="product-name-link"]'
    PRICE_SELECTOR = '[data-test="product-price"]'
    SELLER_SELECTOR = '[data-test="merchant-name"]'
    NOT_FOUND_SELECTOR = ".listing-not-found-block"

    # После loadEventFired сайт продолжает добавлять карточки через JS. Считаем
    # список готовым, когда его длина несколько проверок подряд не меняется.
    CARDS_LOAD_TIMEOUT = 30.0
    CARDS_POLL_INTERVAL = 0.5
    CARDS_STABLE_CHECKS = 3

    def __init__(
            self,
            page: Page,
            *,
            number_pages: int | None = settings.number_pages,
            number_items: int | None = settings.number_items,
            captcha_timeout: float = settings.captcha_timeout,
            page_delay: float = settings.page_delay,
            cards_load_timeout: float = CARDS_LOAD_TIMEOUT,
            cards_poll_interval: float = CARDS_POLL_INTERVAL,
            cards_stable_checks: int = CARDS_STABLE_CHECKS,
    ) -> None:
        super().__init__(
            page,
            number_pages=number_pages,
            page_delay=page_delay,
            navigation_timeout=captcha_timeout,
        )
        self.number_items = number_items
        self.captcha_timeout = captcha_timeout
        self.cards_load_timeout = cards_load_timeout
        self.cards_poll_interval = cards_poll_interval
        self.cards_stable_checks = cards_stable_checks

    @property
    def _page_ready_selector(self) -> str:
        return f"{self.CARD_SELECTOR}, {self.NOT_FOUND_SELECTOR}, {BLOCKED_SELECTOR}"

    def build_search_url(self, query: str) -> str:
        return f"{settings.base_url}/catalog/?q={quote(query)}"

    def build_page_url(self, search_url: str, page_number: int) -> str:
        """Ссылка на страницу N там, куда привёл поиск.

        Поиск по запросу может остаться на /catalog/?q=..., а может увести на
        страницу категории /catalog/iphone-16/#?related_search=... — листать
        надо то, где оказались. Разбивка в обоих случаях одна: page-N/ в конце
        пути, остальное от адреса не меняется.
        """
        parts = urlsplit(search_url)
        path = f"{parts.path.rstrip('/')}/page-{page_number}/"
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

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
        return urljoin(settings.base_url, href) if href else ""

    async def _parse_card(self, card_element: Element) -> CardToPars | None:
        card_link = await self._get_card_link(card_element)
        if not card_link:
            return None

        price = await self._get_text(card_element, self.PRICE_SELECTOR)
        card = CardToPars(
            title=await self._get_text(card_element, self.TITLE_SELECTOR),
            price=price,
            seller=await self._get_text(card_element, self.SELLER_SELECTOR),
            card_link=card_link,
            # цену показывают только у того, что можно купить
            stock=Stock.IN_STOCK if price else Stock.OUT_OF_STOCK,
        )
        # цену не требуем: карточка без неё — это товар не в наличии
        if not (card.title and card.seller):
            return None

        return card

    async def parse_current_page(self) -> list[CardToPars]:
        """Разобрать все карточки открытой страницы выдачи."""
        print("Начинаем парсить страницу...")
        cards: list[CardToPars] = []
        async with self.page.domain_enabled(self.page.cdp.DOM):
            selected_cards = await self.page.select_all(self.CARD_SELECTOR)
            if self.number_items is not None:
                selected_cards = selected_cards[: self.number_items]

            for card_element in selected_cards:
                card = await self._parse_card(card_element)
                if card is not None:
                    cards.append(card)

        return cards

    async def wait_page_state(self) -> PageState:
        await self.page.wait_for_selector(
            self._page_ready_selector,
            state=ElementState.ATTACHED,
            timeout=self.captcha_timeout,
        )

        if await self._is_blocked():
            return PageState.BLOCKED
        if await self._is_not_found_page():
            return PageState.NOT_FOUND
        return PageState.READY

    async def _is_blocked(self) -> bool:
        return await is_blocked_page(self.page)

    async def _is_not_found_page(self) -> bool:
        return (
                await self.page.select(selector=self.NOT_FOUND_SELECTOR) is not None
        )

    async def _card_count(self) -> int:
        return len(await self.page.select_all(self.CARD_SELECTOR))

    async def wait_content_ready(self) -> None:
        """Дождаться стабилизации числа карточек открытой страницы."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.cards_load_timeout
        last_count = -1
        stable_checks = 0

        while True:
            try:
                current_count = await self._card_count()
            except ProtocolError:
                current_count = -1

            if current_count > 0:
                if current_count == last_count:
                    stable_checks += 1
                else:
                    stable_checks = 1
                if stable_checks >= self.cards_stable_checks:
                    return
            else:
                stable_checks = 0

            if loop.time() >= deadline:
                return

            last_count = current_count
            await asyncio.sleep(self.cards_poll_interval)

    def item_key(self, item: CardToPars) -> str:
        return item.card_link


class MegamarketCardParser:
    """Сбор ссылок на продавцов по карточкам товаров.

    В выдаче есть только имя продавца, ссылка на его магазин — на странице
    карточки, поэтому карточку приходится открывать. Но продавцы в выдаче
    повторяются, поэтому в карточку заходим один раз на продавца, а остальным
    его карточкам проставляем уже найденную ссылку.
    """

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
            number_visits: int | None = settings.number_visits,
            captcha_timeout: float = settings.captcha_timeout,
            popover_timeout: float = settings.popover_timeout,
            card_delay: float = settings.card_delay,
    ) -> None:
        self.page = page
        self.number_visits = number_visits
        self.captcha_timeout = captcha_timeout
        self.popover_timeout = popover_timeout
        self.card_delay = card_delay
        self._seller_links: dict[str, str] = {}
        self._visits = 0

    @property
    def _page_ready_selector(self) -> str:
        return (
            f"{self.MERCHANT_LINK_SELECTOR}, {self.MERCHANT_NAME_SELECTOR}, "
            f"{BLOCKED_SELECTOR}"
        )

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
        path = urlsplit(urljoin(settings.base_url, href)).path
        if not path.startswith(cls.SHOP_PATH):
            return ""
        slug = path[len(cls.SHOP_PATH):].strip("/").split("/")[0]
        return f"{settings.base_url}{cls.SHOP_PATH}{slug}/" if slug else ""

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

        if await is_blocked_page(self.page):
            raise SiteBlocked(BLOCKED_MESSAGE)

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

            if self._visits:
                await asyncio.sleep(self.card_delay)

            self._visits += 1
            try:
                shop_link = await self._parse_seller_link(card)
            except SiteBlocked:
                print(
                    f"{BLOCKED_MESSAGE} Отдаём собранное, "
                    f"продавцов найдено: {len(self._seller_links)}."
                )
                break
            self._seller_links[key] = shop_link
            card.seller_link = shop_link

        print(
            f"Продавцов найдено: {len(self._seller_links)}, "
            f"открыто карточек: {self._visits}"
        )
        return list(cards)
