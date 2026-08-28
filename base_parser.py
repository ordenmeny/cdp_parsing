import asyncio
from abc import ABC, abstractmethod
from collections.abc import Hashable, Sequence
from enum import StrEnum

from parsek_cdp import Page, ProtocolError


class PageState(StrEnum):
    READY = "ready"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"


class BasePaginatedParser[T](ABC):
    """Общий поток последовательного парсинга страниц через CDP.

    Наследник описывает только особенности сайта: построение URL, признаки
    состояния страницы, ожидание динамического содержимого и разбор элементов.
    """

    def __init__(
            self,
            page: Page,
            *,
            number_pages: int | None,
            page_delay: float,
            navigation_timeout: float,
    ) -> None:
        self.page = page
        self.number_pages = number_pages
        self.page_delay = page_delay
        self.navigation_timeout = navigation_timeout

        self._search_page_url = ""
        self._seen_item_keys: set[Hashable] = set()

    @abstractmethod
    def build_search_url(self, query: str) -> str:
        """Сформировать адрес первой страницы поиска."""

    @abstractmethod
    def build_page_url(self, search_url: str, page_number: int) -> str:
        """Сформировать адрес страницы с указанным номером."""

    @abstractmethod
    async def wait_page_state(self) -> PageState:
        """Дождаться значимой разметки и определить состояние страницы."""

    @abstractmethod
    async def wait_content_ready(self) -> None:
        """Дождаться окончания динамической отрисовки содержимого."""

    @abstractmethod
    async def parse_current_page(self) -> list[T]:
        """Разобрать элементы открытой страницы."""

    @abstractmethod
    def item_key(self, item: T) -> Hashable:
        """Вернуть устойчивый ключ элемента для дедупликации."""

    async def _current_url(self) -> str:
        """Получить фактический URL после возможного редиректа."""
        return await self.page.evaluate("location.href") or ""

    async def _open_search(self, query: str) -> PageState:
        url = self.build_search_url(query)
        print(f"Переходим на страницу 1: {url}")
        await self.page.navigate(
            url,
            wait_load=True,
            timeout=self.navigation_timeout,
        )
        state = await self.wait_page_state()
        if state is not PageState.READY:
            return state

        self._search_page_url = await self._current_url()
        if self._search_page_url != url:
            print(f"Поиск увёл на: {self._search_page_url}")
        await self.wait_content_ready()
        return state

    async def _go_to_next_page(self, page_number: int) -> PageState:
        await asyncio.sleep(self.page_delay)
        url = self.build_page_url(self._search_page_url, page_number)
        print(f"Переходим на страницу {page_number}: {url}")
        await self.page.navigate(
            url,
            wait_load=True,
            timeout=self.navigation_timeout,
        )
        state = await self.wait_page_state()
        if state is PageState.READY:
            await self.wait_content_ready()
        return state

    def _only_new_items(self, items: Sequence[T]) -> list[T]:
        result: list[T] = []
        for item in items:
            key = self.item_key(item)
            if key in self._seen_item_keys:
                continue
            self._seen_item_keys.add(key)
            result.append(item)
        return result

    @staticmethod
    def _print_stop(state: PageState, page_number: int, collected: int) -> None:
        if state is PageState.BLOCKED:
            print(
                "Сайт решил, что запросы автоматические. "
                f"Отдаём собранное, элементов: {collected}."
            )
        elif state is PageState.NOT_FOUND:
            print(
                f"Страница {page_number} не содержит результатов. "
                "Останавливаемся."
            )

    async def parse(self, query: str) -> list[T]:
        """Последовательно открыть и разобрать страницы выдачи."""
        all_items: list[T] = []
        self._search_page_url = ""
        self._seen_item_keys.clear()

        if self.number_pages is not None and self.number_pages < 1:
            return all_items

        try:
            state = await self._open_search(query)
        except TimeoutError:
            print("Страница 1 не открылась. Отдаём пустой результат.")
            return all_items

        if state is not PageState.READY:
            self._print_stop(state, page_number=1, collected=0)
            return all_items

        page_number = 1
        while True:
            try:
                page_items = await self.parse_current_page()
            except ProtocolError as error:
                print(
                    f"Страница {page_number} перерисовалась во время разбора: "
                    f"{error}. Отдаём собранное, элементов: {len(all_items)}."
                )
                break

            new_items = self._only_new_items(page_items)
            print(
                f"На странице {page_number} собрано элементов: {len(new_items)}"
            )
            all_items.extend(new_items)

            if not new_items:
                print(
                    f"На странице {page_number} нет новых элементов. "
                    "Останавливаемся."
                )
                break

            if self.number_pages is not None and page_number >= self.number_pages:
                break

            page_number += 1
            try:
                state = await self._go_to_next_page(page_number)
            except TimeoutError:
                print(
                    f"Страница {page_number} не открылась. "
                    f"Отдаём собранное, элементов: {len(all_items)}."
                )
                break

            if state is not PageState.READY:
                self._print_stop(state, page_number, len(all_items))
                break

        return all_items
