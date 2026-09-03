import asyncio
from abc import ABC, abstractmethod
from collections.abc import Hashable, Sequence
from enum import StrEnum
from urllib.parse import urlsplit

from parsek_cdp import Page, ProtocolError
from websockets.exceptions import ConnectionClosed

import utils
from cdp_metrics import CDPMetrics


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
            start_page: int,
            page_delay_min: int,
            page_delay_max: int,
            long_pause_every_pages: int,
            long_pause_min: int,
            long_pause_max: int,
            navigation_timeout: float,
            repeat_pages_limit: int = 2,
            repeat_new_share: float = 0.25,
            cdp_metrics: CDPMetrics | None = None,
    ) -> None:
        if start_page < 1:
            raise ValueError("Номер начальной страницы должен быть не меньше 1.")
        if long_pause_every_pages < 1:
            raise ValueError("Интервал длинной паузы должен быть не меньше 1.")
        if repeat_pages_limit < 1:
            raise ValueError("Предел повторов должен быть не меньше 1.")
        if not 0 <= repeat_new_share <= 1:
            raise ValueError("Доля новых элементов должна быть от 0 до 1.")
        self.page = page
        self.number_pages = number_pages
        self.start_page = start_page
        self.page_delay_min = page_delay_min
        self.page_delay_max = page_delay_max
        self.long_pause_every_pages = long_pause_every_pages
        self.long_pause_min = long_pause_min
        self.long_pause_max = long_pause_max
        self.navigation_timeout = navigation_timeout
        self.repeat_pages_limit = repeat_pages_limit
        self.repeat_new_share = repeat_new_share
        self.cdp_metrics = cdp_metrics

        self._search_page_url = ""
        self._seen_item_keys: set[Hashable] = set()
        # Прирост новых элементов по страницам текущего прогона: с ним
        # сравниваем, чтобы отличить кольцо выдачи от нормального сбора.
        self._new_item_counts: list[int] = []
        self.interrupted = False

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

    async def _parse_current_page_measured(self, page_number: int) -> list[T]:
        if self.cdp_metrics is None:
            return await self.parse_current_page()

        before = self.cdp_metrics.snapshot()
        try:
            return await self.parse_current_page()
        finally:
            self.cdp_metrics.print_summary(
                f"разбор страницы {page_number}",
                since=before,
            )

    async def prepare_first_page(self) -> PageState:
        """При необходимости подготовить первую страницу перед разбором."""
        return PageState.READY

    async def _current_url(self) -> str:
        """Получить фактический URL после возможного редиректа."""
        return await self.page.evaluate("location.href") or ""

    @staticmethod
    def _same_navigation_url(actual: str, expected: str) -> bool:
        """Совпадают ли адрес, путь и query после возможной нормализации hash."""
        actual_parts = urlsplit(actual)
        expected_parts = urlsplit(expected)
        return (
            actual_parts.scheme,
            actual_parts.netloc,
            actual_parts.path.rstrip("/"),
            actual_parts.query,
        ) == (
            expected_parts.scheme,
            expected_parts.netloc,
            expected_parts.path.rstrip("/"),
            expected_parts.query,
        )

    async def _wait_for_navigation_url(self, expected: str) -> str:
        """Дождаться фиксации нового URL, не полагаясь на loadEventFired."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + min(self.navigation_timeout, 30.0)

        while True:
            try:
                actual = await self._current_url()
            except ProtocolError:
                # Во время смены документа execution context кратко недоступен.
                actual = ""
            if self._same_navigation_url(actual, expected):
                return actual
            if loop.time() >= deadline:
                raise TimeoutError
            await asyncio.sleep(0.5)

    async def _open_search(self, query: str) -> PageState:
        url = self.build_search_url(query)
        print(f"Открываем исходную страницу поиска: {url}")
        await self.page.navigate(
            url,
            wait_load=True,
            timeout=self.navigation_timeout,
        )

        # Сначала фиксируем адрес после серверного или клиентского редиректа.
        # Наследник может учитывать тип фактически открытой страницы уже при
        # ожидании её разметки.
        self._search_page_url = await self._current_url()
        if self._search_page_url != url:
            print(f"Поиск увёл на: {self._search_page_url}")

        state = await self.wait_page_state()
        if state is not PageState.READY:
            return state

        await self.wait_content_ready()
        return state

    async def _go_to_next_page(
            self,
            page_number: int,
            *,
            parsed_pages: int = 0,
    ) -> PageState:
        if (
            parsed_pages > 0
            and parsed_pages % self.long_pause_every_pages == 0
        ):
            await self._sleep_long_pause(page_number, parsed_pages)
        else:
            await self._sleep_page_delay(
                f"перед переходом на страницу {page_number}",
            )
        url = self.build_page_url(self._search_page_url, page_number)
        print(f"Переходим на страницу {page_number}: {url}")
        # У SPA и страниц с hash-фильтрами loadEventFired может не прийти даже
        # после фактической смены документа. Отправляем навигацию без ожидания
        # этого события, затем подтверждаем новый адрес напрямую.
        await self.page.navigate(
            url,
            wait_load=False,
        )
        actual_url = await self._wait_for_navigation_url(url)
        print(f"Страница {page_number} открыта: {actual_url}")

        state = await self.wait_page_state()
        if state is PageState.READY:
            await self.wait_content_ready()
        return state

    async def _sleep_page_delay(self, reason: str) -> None:
        delay = utils.get_random_delay(
            self.page_delay_min,
            self.page_delay_max,
        )
        print(f"Ждём {delay} сек. {reason}.")
        if delay:
            await asyncio.sleep(delay)

    async def _sleep_long_pause(
            self,
            next_page_number: int,
            parsed_pages: int,
    ) -> None:
        delay = utils.get_random_delay(
            self.long_pause_min,
            self.long_pause_max,
        )
        print(
            f"Собрано страниц за текущий запуск: {parsed_pages}. "
            f"Ждём {delay} сек. перед переходом "
            f"на страницу {next_page_number}."
        )
        if delay:
            await asyncio.sleep(delay)

    def _only_new_items(self, items: Sequence[T]) -> list[T]:
        result: list[T] = []
        for item in items:
            key = self.item_key(item)
            if key in self._seen_item_keys:
                continue
            self._seen_item_keys.add(key)
            result.append(item)
        return result

    def _is_repeat_page(
            self,
            page_items: Sequence[T],
            new_items: Sequence[T],
    ) -> bool:
        """Повторяет ли страница уже собранное.

        Дойдя до конца выдачи, сайт может начать её сначала: после 64-й
        страницы отдать вторую. Точного совпадения при этом не будет — цены и
        наличие успевают измениться, — поэтому сравниваем не содержимое, а
        прирост: сколько новых элементов дала страница против обычного для
        этого прогона. Долю от размера страницы брать нельзя — на
        накопительной выдаче она падает сама собой, хотя сбор идёт нормально.
        """
        if not page_items:
            return True
        if not new_items:
            return True
        self._new_item_counts.append(len(new_items))
        # Первую страницу прогона за эталон не берём: при продолжении с
        # середины она приносит начало списка разом и завысила бы норму.
        baseline = max(self._new_item_counts[1:], default=0)
        return len(new_items) < self.repeat_new_share * baseline

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
        self._new_item_counts.clear()
        self.interrupted = False

        if self.number_pages is not None and self.number_pages < 1:
            return all_items

        try:
            state = await self._open_search(query)
        except TimeoutError:
            print("Исходная страница поиска не открылась. Отдаём пустой результат.")
            return all_items
        except (ConnectionError, ConnectionClosed, ProtocolError):
            self.interrupted = True
            print("Поисковая вкладка закрыта. Отдаём пустой результат.")
            return all_items

        if state is not PageState.READY:
            self._print_stop(state, page_number=1, collected=0)
            return all_items

        try:
            state = await self.prepare_first_page()
        except (ConnectionError, ConnectionClosed, ProtocolError):
            self.interrupted = True
            print("Поисковая вкладка закрыта. Отдаём пустой результат.")
            return all_items
        if state is not PageState.READY:
            self._print_stop(state, page_number=1, collected=0)
            return all_items

        # Подготовка может изменить query или fragment (например, фильтром).
        try:
            self._search_page_url = await self._current_url()
        except (ConnectionError, ConnectionClosed, ProtocolError):
            self.interrupted = True
            print("Поисковая вкладка закрыта. Отдаём пустой результат.")
            return all_items

        # Для продолжения сначала обязательно получаем канонический адрес
        # обычного поиска после редиректа и применения фильтра. Только затем
        # строим страницу, с которой пользователь попросил начать разбор.
        if self.start_page > 1:
            try:
                state = await self._go_to_next_page(self.start_page)
            except TimeoutError:
                print(
                    f"Страница {self.start_page} не открылась. "
                    "Отдаём пустой результат."
                )
                return all_items
            except (ConnectionError, ConnectionClosed, ProtocolError):
                self.interrupted = True
                print("Поисковая вкладка закрыта. Отдаём пустой результат.")
                return all_items
            if state is not PageState.READY:
                self._print_stop(state, page_number=self.start_page, collected=0)
                return all_items

        page_number = self.start_page
        parsed_pages = 0
        repeated_pages = 0
        while True:
            print(f"Начинаем парсить страницу {page_number}...")
            try:
                page_items = await self._parse_current_page_measured(page_number)
            except (ConnectionError, ConnectionClosed):
                self.interrupted = True
                print(
                    "Поисковая вкладка закрыта. "
                    f"Отдаём собранное, элементов: {len(all_items)}."
                )
                break
            except ProtocolError as error:
                self.interrupted = True
                print(
                    f"Страница {page_number} закрылась или перерисовалась: "
                    f"{error}. Отдаём собранное, элементов: {len(all_items)}."
                )
                break

            new_items = self._only_new_items(page_items)
            print(
                f"На странице {page_number} собрано элементов: {len(new_items)}"
            )
            all_items.extend(new_items)
            parsed_pages += 1

            if self._is_repeat_page(page_items, new_items):
                repeated_pages += 1
                print(
                    f"На странице {page_number} новых элементов "
                    f"{len(new_items)} из {len(page_items)}: выдача повторяет "
                    f"собранное ({repeated_pages} подряд из "
                    f"{self.repeat_pages_limit})."
                )
                if repeated_pages >= self.repeat_pages_limit:
                    print(
                        "Похоже, выдача пошла по кругу. Останавливаемся, "
                        f"элементов: {len(all_items)}."
                    )
                    break
            else:
                repeated_pages = 0

            if self.number_pages is not None and parsed_pages >= self.number_pages:
                break

            page_number += 1
            try:
                state = await self._go_to_next_page(
                    page_number,
                    parsed_pages=parsed_pages,
                )
            except TimeoutError:
                print(
                    f"Страница {page_number} не открылась. "
                    f"Отдаём собранное, элементов: {len(all_items)}."
                )
                break
            except (ConnectionError, ConnectionClosed, ProtocolError):
                self.interrupted = True
                print(
                    "Поисковая вкладка закрыта. "
                    f"Отдаём собранное, элементов: {len(all_items)}."
                )
                break

            if state is not PageState.READY:
                self._print_stop(state, page_number, len(all_items))
                break

        return all_items
