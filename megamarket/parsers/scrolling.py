"""Сбор выдачи Megamarket догрузкой на месте, без перехода по страницам.

Отдельный поток: документ открывается один раз, а новые карточки появляются
после нажатия «Показать ещё» — так же, как у живого пользователя. Постраничный
обход (``page-N`` в адресе) здесь не используется вовсе; общими остаются только
селекторы карточек, проба состояния страницы и фильтр «В наличии».
"""

import asyncio

from parsek_cdp import Element, ProtocolError
from websockets.exceptions import ConnectionClosed

from megamarket import utils
from megamarket.parsers.base_parser import PageState
from megamarket.config import settings
from megamarket.domain import CardToPars
from megamarket.parsers.parsing import BLOCKED_HEADING, BLOCKED_MESSAGE, MegamarketParsePage


class MegamarketScrollPage(MegamarketParsePage):
    """Набирает выдачу в одном документе, нажимая «Показать ещё».

    От постраничного парсера отличается только методом ``parse``: разбор
    карточек, ожидание готовности и включение фильтра унаследованы без
    изменений, а вся навигация по номерам страниц не задействована.
    """

    # Класс висит на обёртке, кликабельна вложенная кнопка.
    MORE_BUTTON_SELECTOR = ".pui-pagination__more-button button"

    # Точка внутри окна, над которой крутим колесо, и шаг прокрутки.
    SCROLL_POINT = (400.0, 400.0)
    SCROLL_DELTA = 600.0
    SCROLL_STEPS = 4
    SCROLL_STEP_DELAY = 0.35

    def __init__(
            self,
            page,
            *,
            number_clicks: int | None = settings.parser.number_clicks,
            more_button_timeout: float = settings.parser.more_button_timeout,
            **kwargs,
    ) -> None:
        super().__init__(page, **kwargs)
        self.number_clicks = number_clicks
        self.more_button_timeout = more_button_timeout

    async def _find_more_button(self) -> Element | None:
        """Найти кнопку догрузки; её отсутствие означает конец выдачи."""
        try:
            return await self.page.select(selector=self.MORE_BUTTON_SELECTOR)
        except ProtocolError:
            return None

    async def _scroll_down(self) -> None:
        """Прокрутить вниз настоящим колесом мыши, а не прыжком к элементу."""
        for _ in range(self.SCROLL_STEPS):
            try:
                await self.page.cdp.Input.dispatch_mouse_event(
                    type_="mouseWheel",
                    x=self.SCROLL_POINT[0],
                    y=self.SCROLL_POINT[1],
                    delta_x=0,
                    delta_y=self.SCROLL_DELTA,
                )
            except ProtocolError:
                return
            if self.SCROLL_STEP_DELAY:
                await asyncio.sleep(self.SCROLL_STEP_DELAY)

    async def _wait_cards_grew(self, before: int) -> bool:
        """Дождаться прироста карточек после нажатия кнопки."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.more_button_timeout

        while True:
            try:
                current = (await self._probe_page()).cards
            except ProtocolError:
                current = before
            if current > before:
                # Порция приезжает не мгновенно: даём списку устаканиться.
                await self.wait_content_ready()
                return True
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(self.cards_poll_interval)

    async def _sleep_before_more(self, clicks: int) -> None:
        """Выдержать паузу перед догрузкой в том же ритме, что и обход страниц."""
        if clicks and clicks % self.long_pause_every_pages == 0:
            delay = utils.get_random_delay(
                self.long_pause_min,
                self.long_pause_max,
            )
            print(
                f"Догрузок за текущий запуск: {clicks}. "
                f"Ждём {delay} сек. перед следующей."
            )
        else:
            delay = utils.get_random_delay(
                self.page_delay_min,
                self.page_delay_max,
            )
            print(f"Ждём {delay} сек. перед догрузкой {clicks + 1}.")
        if delay:
            await asyncio.sleep(delay)

    async def _load_more(self, clicks: int) -> bool:
        """Догрузить очередную порцию. ``False`` — продолжать нечем."""
        if await self._find_more_button() is None:
            print("Кнопки «Показать ещё» нет — выдача закончилась.")
            return False

        await self._sleep_before_more(clicks)
        await self._scroll_down()

        # Кнопку ищем заново: список успел перерисоваться, и прежний узел
        # мог устареть, пока мы ждали и прокручивали страницу.
        button = await self._find_more_button()
        if button is None:
            print("Кнопка «Показать ещё» пропала во время прокрутки.")
            return False

        before = (await self._probe_page()).cards
        print(f"Нажимаем «Показать ещё» ({clicks + 1}). Карточек сейчас: {before}.")
        await button.mouse_click()

        if await self._wait_cards_grew(before):
            return True

        # Прироста нет — отличаем штатный конец выдачи от блокировки.
        probe = await self._probe_page()
        if BLOCKED_HEADING in probe.heading.casefold():
            print(f"{BLOCKED_MESSAGE} Останавливаемся.")
            return False
        if await self._find_more_button() is None:
            print("Кнопка исчезла после нажатия — выдача закончилась.")
            return False
        print(
            "Кнопка на месте, но карточек не прибавилось за "
            f"{self.more_button_timeout:g} сек. Останавливаемся: похоже, "
            "догрузку не отдали."
        )
        return False

    async def parse(self, query: str) -> list[CardToPars]:
        """Открыть выдачу один раз и добирать её нажатиями «Показать ещё»."""
        all_items: list[CardToPars] = []
        self._search_page_url = ""
        self._seen_item_keys.clear()
        self._new_item_counts.clear()
        self.interrupted = False

        if self.number_clicks is not None and self.number_clicks < 0:
            return all_items

        try:
            state = await self._open_search(query)
            if state is PageState.READY:
                state = await self.prepare_first_page()
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

        clicks = 0
        repeated_loads = 0
        while True:
            print(f"Разбираем выдачу после {clicks} догрузок...")
            try:
                items = await self._parse_current_page_measured(clicks + 1)
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
                    f"Страница закрылась или перерисовалась: {error}. "
                    f"Отдаём собранное, элементов: {len(all_items)}."
                )
                break

            new_items = self._only_new_items(items)
            all_items.extend(new_items)
            print(
                f"Новых элементов: {len(new_items)}. "
                f"Всего собрано: {len(all_items)}."
            )

            # Признак кольца тот же, что и при обходе страниц: прирост
            # заметно меньше обычного для этого прогона.
            if self._is_repeat_page(items, new_items):
                repeated_loads += 1
                print(
                    "Догрузка не принесла новых элементов "
                    f"({repeated_loads} подряд из {self.repeat_pages_limit})."
                )
                if repeated_loads >= self.repeat_pages_limit:
                    print(
                        "Похоже, выдача пошла по кругу. Останавливаемся, "
                        f"элементов: {len(all_items)}."
                    )
                    break
            else:
                repeated_loads = 0

            if self.number_clicks is not None and clicks >= self.number_clicks:
                print(f"Достигнут предел догрузок: {self.number_clicks}.")
                break

            try:
                if not await self._load_more(clicks):
                    break
            except (ConnectionError, ConnectionClosed, ProtocolError):
                self.interrupted = True
                print(
                    "Поисковая вкладка закрыта. "
                    f"Отдаём собранное, элементов: {len(all_items)}."
                )
                break
            clicks += 1

        return all_items
