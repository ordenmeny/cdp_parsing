import asyncio
import json
from collections.abc import Sequence
from urllib.parse import parse_qs, quote, urljoin, urlsplit, urlunsplit

from parsek_cdp import Browser, Element, ElementState, Page, ProtocolError
from websockets.exceptions import ConnectionClosed

from base_parser import BasePaginatedParser, PageState
from config import settings
from domain import CardToPars, Stock
from utils import normalize_text

# Вместо страницы сайт может отдать заглушку «запросы похожи на автоматические».
# Узнаём её по заголовку: он говорит об этом прямым текстом. Разметку заглушки
# для этого не используем — id ниже нужен только чтобы не ждать её впустую.
BLOCKED_HEADING = "запросы с вашего устройства похожи на автоматические"
BLOCKED_SELECTOR = "#request-id"
BLOCKED_MESSAGE = "Сайт решил, что запросы автоматические."


def is_brand_page_url(url: str) -> bool:
    """Ведёт ли фактический URL на страницу бренда Megamarket."""
    path_parts = [part for part in urlsplit(url).path.split("/") if part]
    return bool(path_parts) and path_parts[0] == "brands"


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
    # Разные сборки сайта размечают основные карточки по-разному: обычная
    # выдача использует data-list-id="main", брендовая — schema.org itemprop.
    # Объединение покрывает оба варианта и не захватывает рекламные карусели.
    CARD_SELECTOR = (
        '[data-test="product-item"][data-list-id="main"], '
        '[data-test="product-item"][itemprop="itemListElement"]'
    )
    TITLE_SELECTOR = '[data-test="product-name-link"]'
    PRICE_SELECTOR = '[data-test="product-price"]'
    SELLER_SELECTOR = '[data-test="merchant-name"]'
    IMAGE_SELECTOR = 'meta[itemprop="image"][content]'
    NOT_FOUND_SELECTOR = ".listing-not-found-block"
    IN_STOCK_TOGGLE_SELECTOR = ".pui-toggle"
    IN_STOCK_LABEL_SELECTOR = ".pui-toggle__label span"
    IN_STOCK_CONTROL_SELECTOR = ".pui-toggle-control"
    IN_STOCK_SELECTED_CLASS = "pui-toggle-control_selected"

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
            filter_timeout: float = settings.filter_timeout,
            page_delay: float = settings.page_delay,
            cards_load_timeout: float = CARDS_LOAD_TIMEOUT,
            cards_poll_interval: float = CARDS_POLL_INTERVAL,
            cards_stable_checks: int = CARDS_STABLE_CHECKS,
            in_stock_only: bool = False,
    ) -> None:
        super().__init__(
            page,
            number_pages=number_pages,
            page_delay=page_delay,
            navigation_timeout=captcha_timeout,
        )
        self.number_items = number_items
        self.captcha_timeout = captcha_timeout
        self.filter_timeout = filter_timeout
        self.cards_load_timeout = cards_load_timeout
        self.cards_poll_interval = cards_poll_interval
        self.cards_stable_checks = cards_stable_checks
        self.in_stock_only = in_stock_only

    @property
    def is_brand_page(self) -> bool:
        """Перенаправил ли поиск на каталог конкретного бренда."""
        return is_brand_page_url(self._search_page_url)

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

    async def _find_in_stock_control(self) -> tuple[Element, bool] | None:
        """Найти toggle по подписи, не полагаясь на сложный XPath."""
        try:
            toggles = await self.page.select_all(self.IN_STOCK_TOGGLE_SELECTOR)
        except ProtocolError:
            return None

        for toggle in toggles:
            label = await toggle.query_selector(self.IN_STOCK_LABEL_SELECTOR)
            if label is None:
                continue
            if normalize_text(label.text).casefold() != "в наличии":
                continue
            control = await toggle.query_selector(self.IN_STOCK_CONTROL_SELECTOR)
            if control is None:
                continue
            classes = control.attributes.get("class", "").split()
            return control, self.IN_STOCK_SELECTED_CLASS in classes
        return None

    async def _wait_for_in_stock_control(
            self,
            *,
            selected: bool | None = None,
    ) -> tuple[Element, bool]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.filter_timeout

        while True:
            result = await self._find_in_stock_control()
            if result is not None and (selected is None or result[1] is selected):
                return result
            if loop.time() >= deadline:
                raise TimeoutError
            await asyncio.sleep(0.1)

    async def prepare_first_page(self) -> PageState:
        """При включённом флаге выбрать фильтр перед разбором выдачи."""
        if self.is_brand_page:
            print("Распознана страница бренда.")

        if not self.in_stock_only:
            return PageState.READY

        print("Включаем фильтр «В наличии»...")
        try:
            control, selected = await self._wait_for_in_stock_control()
        except TimeoutError as error:
            raise RuntimeError(
                "Переключатель «В наличии» не появился в DOM за "
                f"{self.filter_timeout:g} секунд."
            ) from error

        print("Переключатель «В наличии» найден.")
        if not selected:
            await control.mouse_click()
            print("Клик по переключателю выполнен. Ждём включения фильтра...")
        # https://megamarket.ru/promo-page/details/#?slug=smartfon-apple-iphone-17-pro-max-512gb-cosmic-orange-bez-rustore-700001132174_254730&merchantId=254730&exclusiveMerchantId=254730&exclusiveWarehouseId=3352735
        try:
            await self._wait_for_in_stock_control(selected=True)
        except TimeoutError as error:
            raise RuntimeError(
                "Клик выполнен, но фильтр «В наличии» не включился за "
                f"{self.filter_timeout:g} секунд."
            ) from error
        print("Фильтр «В наличии» включён.")

        # Даём приложению начать обновление выдачи, затем ждём её стабилизации.
        if self.page_delay:
            await asyncio.sleep(self.page_delay)

        state = await self.wait_page_state()
        if state is PageState.READY:
            await self.wait_content_ready()
        return state

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

        card = CardToPars(
            title=await self._get_text(card_element, self.TITLE_SELECTOR),
            price=await self._get_text(card_element, self.PRICE_SELECTOR),
            seller=await self._get_text(card_element, self.SELLER_SELECTOR),
            card_link=card_link,
            image_link=await self._get_attribute(
                card_element,
                self.IMAGE_SELECTOR,
                "content",
            ),
            # Основной запуск собирает выдачу уже с фильтром «В наличии».
            stock=Stock.IN_STOCK,
        )
        # Цену не требуем: у некоторых карточек она может появиться позже.
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


class MegamarketParseCard:
    """Получение ссылки продавца из модального окна карточки товара."""

    SHOP_PATH = "/shop/"
    MERCHANT_NAME_SELECTOR = ".pdp-merchant-rating-block__merchant-name"
    SELLER_LINK_SELECTOR = (
        ".pdp-merchant-rating-block__popover "
        "a.pdp-merchant-rating-block__merchant-all-products-link-button[href]"
    )

    def __init__(
            self,
            browser: Browser,
            cards: Sequence[CardToPars],
            *,
            captcha_timeout: float = settings.captcha_timeout,
            popover_timeout: float = settings.popover_timeout,
            card_delay: float = settings.card_delay,
            card_close_delay: float = settings.card_close_delay,
            number_visits: int | None = settings.number_visits,
    ) -> None:
        self.browser = browser
        self.cards = list(cards)
        self.captcha_timeout = captcha_timeout
        self.popover_timeout = popover_timeout
        self.card_delay = card_delay
        self.card_close_delay = card_close_delay
        self.number_visits = number_visits

        self._seller_links: dict[str, str] = {}
        self._visits = 0
        self._blocked = False
        self._interrupted = False
        for card in self.cards:
            if card.seller_link:
                self._seller_links.setdefault(
                    self._seller_key(card),
                    card.seller_link,
                )

    @property
    def _page_ready_selector(self) -> str:
        return f"{self.MERCHANT_NAME_SELECTOR}, {BLOCKED_SELECTOR}"

    def get_cards(self) -> list[CardToPars]:
        """Вернуть карточки, переданные парсеру при создании."""
        return list(self.cards)

    @staticmethod
    def _merchant_id(card_link: str) -> str:
        """Получить идентификатор продавца из query или fragment ссылки."""
        parts = urlsplit(card_link)
        params = parse_qs(parts.query) | parse_qs(parts.fragment.lstrip("#?"))
        found = params.get("merchantId") or params.get("exclusiveMerchantId")
        return found[0] if found else ""

    @classmethod
    def _seller_key(cls, card: CardToPars) -> str:
        """Различать продавцов по id, а при его отсутствии — по имени."""
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

    async def _wait_for_seller_name(self, page: Page, expected: str) -> bool:
        """Дождаться данных новой карточки после обычной или hash-навигации."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.popover_timeout
        expression = (
            f"(document.querySelector({json.dumps(self.MERCHANT_NAME_SELECTOR)}) "
            "|| {}).textContent || ''"
        )
        expected = normalize_text(expected).casefold()

        while True:
            current = await page.evaluate(expression)

            if normalize_text(current or "").casefold() == expected:
                return True
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(0.1)

    async def _parse_seller_link(self, card: CardToPars) -> str:
        """Открыть карточку в новой вкладке и получить ссылку продавца."""
        print(f"Открываем карточку продавца «{card.seller}»: {card.card_link}")
        page = await self.browser.new_page()
        try:
            try:
                await page.navigate(
                    card.card_link,
                    # У promo-page карточки отличаются fragment-частью URL.
                    # Такая навигация не обязана породить loadEventFired.
                    wait_load=False,
                    timeout=self.captcha_timeout,
                )
                await page.wait_for_selector(
                    self._page_ready_selector,
                    state=ElementState.ATTACHED,
                    timeout=self.captcha_timeout,
                )
            except TimeoutError:
                print(f"Карточка не открылась: {card.card_link}")
                return ""

            if await is_blocked_page(page):
                print(f"{BLOCKED_MESSAGE} Ссылку продавца не собираем.")
                self._blocked = True
                return ""

            if not await self._wait_for_seller_name(page, card.seller):
                print(
                    f"Карточка продавца «{card.seller}» не успела обновиться."
                )
                return ""

            seller_element = await page.select(selector=self.MERCHANT_NAME_SELECTOR)
            if seller_element is None:
                print(f"Название продавца «{card.seller}» на странице не найдено.")
                return ""

            try:
                await seller_element.mouse_click()
                link_element = await page.wait_for_selector(
                    self.SELLER_LINK_SELECTOR,
                    state=ElementState.ATTACHED,
                    timeout=self.popover_timeout,
                )
            except TimeoutError:
                print(f"Модальное окно продавца «{card.seller}» не открылось.")
                return ""

            shop_link = ""
            if link_element is not None:
                shop_link = self._normalize_shop_link(
                    link_element.attributes.get("href", "")
                )

            print(f"Ссылка продавца: {shop_link or 'не найдена'}")
            return shop_link
        except (ConnectionError, ConnectionClosed, ProtocolError):
            self._interrupted = True
            print(
                "Вкладка карточки закрыта вручную. "
                "Останавливаем сбор ссылок и сохраняем результат."
            )
            return ""
        finally:
            # После обработки оставляем карточку открытой на заданное время.
            # Если вкладку закрыл оператор, дополнительная пауза не нужна.
            if self.card_close_delay and not self._interrupted:
                print(
                    "Карточка обработана. "
                    f"Закрываем вкладку через {self.card_close_delay:g} сек."
                )
                await asyncio.sleep(self.card_close_delay)

            # Реально закрываем вкладку, а не только websocket объекта Page.
            # После ручного закрытия target уже уничтожен: второй Page.close()
            # может зависнуть и помешать вызывающему коду сохранить отчёт.
            if not self._interrupted:
                try:
                    await asyncio.wait_for(page.cdp.Page.close(), timeout=2)
                except (
                        TimeoutError,
                        ConnectionError,
                        ConnectionClosed,
                        ProtocolError,
                ):
                    pass

    async def parse(self, card: CardToPars) -> list[CardToPars]:
        """Заполнить ссылку продавца и вернуть весь список карточек."""
        key = self._seller_key(card)
        if card.seller_link:
            self._seller_links.setdefault(key, card.seller_link)
            print(
                f"У продавца «{card.seller}» ссылка уже заполнена, "
                "строку не меняем."
            )
            return self.get_cards()

        if key in self._seller_links:
            card.seller_link = self._seller_links[key]
            print(
                f"Продавец «{card.seller}» уже обработан, "
                "карточку повторно не открываем."
            )
            return self.get_cards()

        if self._blocked:
            print("Сайт уже показал блокировку, новые карточки не открываем.")
            return self.get_cards()

        if self._interrupted:
            print("Сбор ссылок остановлен после ручного закрытия вкладки.")
            return self.get_cards()

        if self.number_visits is not None and self._visits >= self.number_visits:
            print(
                f"Достигнут лимит переходов в карточки: {self.number_visits}."
            )
            return self.get_cards()

        # Пауза перед каждым реальным переходом, включая первый. В main.py
        # это не даёт сразу после поисковой выдачи открыть карточку.
        if self.card_delay:
            await asyncio.sleep(self.card_delay)

        self._visits += 1
        shop_link = await self._parse_seller_link(card)
        # Запоминаем даже неудачную попытку: повторный заход к тому же продавцу
        # повышает риск блокировки, но не даёт новой информации.
        self._seller_links[key] = shop_link
        card.seller_link = shop_link
        return self.get_cards()

    async def parse_all(self) -> list[CardToPars]:
        """Обработать список, открывая не более одной карточки на продавца."""
        for card in self.cards:
            await self.parse(card)
            if self._blocked or self._interrupted:
                break
        return self.get_cards()
