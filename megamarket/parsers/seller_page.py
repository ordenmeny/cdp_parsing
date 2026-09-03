"""Разбор страницы магазина Megamarket и её отсутствия.

Отвечает на один вопрос: что лежит по адресу `/shop/<слаг>/`. Ссылка на
магазин у нас угадана слагификатором из названия, поэтому исходов три:
магазина нет, магазин есть, страница молчит. Их важно различать — «не
ответила» не то же самое, что «такого магазина не существует».
"""

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from parsek_cdp import Browser, Page, ProtocolError
from websockets.exceptions import ConnectionClosed

from megamarket.cdp.extractors import SELLER_STATE_SCRIPT, SellerState
from megamarket.config import settings
from megamarket.domain import SellerInfo
from megamarket.exceptions import SiteBlocked
from megamarket.parsers.parsing import BLOCKED_MESSAGE, is_blocked_page


class SellerPageState(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SellerPageResult:
    """Чем закончился заход на страницу магазина."""

    state: SellerPageState
    info: SellerInfo | None = None


def build_seller_info(state: SellerState) -> SellerInfo:
    return SellerInfo(
        seller_id=state.merchant_id,
        name=state.name,
        slug=state.slug,
        official_name=state.official_name,
        ogrn=state.ogrn,
        inn=state.inn,
        email=state.email,
        phone=state.phone,
        legal_form=state.legal_form,
        address=state.address,
        rating=state.rating,
    )


class MegamarketSellerPage:
    """Открывает страницы магазинов и говорит, что на них."""

    def __init__(
            self,
            browser: Browser,
            *,
            navigation_timeout: float = settings.parser.captcha_timeout,
            state_timeout: float = settings.parser.seller_page_timeout,
            poll_interval: float = 0.5,
    ) -> None:
        self.browser = browser
        self.navigation_timeout = navigation_timeout
        self.state_timeout = state_timeout
        self.poll_interval = poll_interval

    async def read_state(self, page: Page) -> SellerState:
        """Дождаться, пока SPA положит состояние в ``window.__APP__``."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.state_timeout
        last = SellerState()

        while True:
            try:
                last = SellerState.from_raw(await page.evaluate(SELLER_STATE_SCRIPT))
            except ProtocolError:
                # Во время смены документа execution context недоступен.
                last = SellerState()
            if last.status_code or last.merchant_id:
                return last
            if loop.time() >= deadline:
                return last
            await asyncio.sleep(self.poll_interval)

    @staticmethod
    def classify(state: SellerState) -> SellerPageResult:
        """Перевести состояние страницы в исход.

        Сначала смотрим код ответа: у несуществующего магазина реквизитов нет
        и быть не может, поэтому 404 старше всего остального.
        """
        if state.status_code == 404:
            return SellerPageResult(SellerPageState.NOT_FOUND)
        if state.merchant_id:
            return SellerPageResult(
                SellerPageState.FOUND,
                build_seller_info(state),
            )
        return SellerPageResult(SellerPageState.UNKNOWN)

    async def parse(self, link: str) -> SellerPageResult:
        """Открыть страницу магазина в отдельной вкладке и разобрать её.

        Заглушка про автоматические запросы — не приговор конкретному
        продавцу, а повод остановить весь обход, поэтому она поднимается
        исключением, а не превращается в исход.
        """
        print(f"Открываем магазин: {link}")
        page = await self.browser.new_page()
        try:
            try:
                await page.navigate(
                    link,
                    wait_load=True,
                    timeout=self.navigation_timeout,
                )
            except TimeoutError:
                print(f"Страница магазина не открылась: {link}")
                return SellerPageResult(SellerPageState.UNKNOWN)

            if await is_blocked_page(page):
                raise SiteBlocked(BLOCKED_MESSAGE)

            result = self.classify(await self.read_state(page))
            if result.state is SellerPageState.NOT_FOUND:
                print("Магазина по этому адресу нет (404).")
            elif result.info is not None:
                print(
                    f"Магазин найден: id={result.info.seller_id} "
                    f"«{result.info.name}», ОГРН {result.info.ogrn or '—'}."
                )
            else:
                print("Состояние страницы не появилось, исход неизвестен.")
            return result
        finally:
            try:
                await asyncio.wait_for(page.cdp.Page.close(), timeout=2)
            except (
                    TimeoutError,
                    ConnectionError,
                    ConnectionClosed,
                    ProtocolError,
            ):
                pass
