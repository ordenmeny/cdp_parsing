import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from parsek_cdp import Browser, ProtocolError
from parsek_cdp.core.target import Target
from websockets.exceptions import ConnectionClosed

from megamarket.cdp.browser_endpoint import connect_browser
from megamarket.cdp.cdp_metrics import collect_cdp_metrics
from megamarket.cdp.parsek_compat import install_parsek_target_race_fix
from megamarket.clients.remote_api import RemoteApiClient
from megamarket.config import settings
from megamarket.domain import CardToPars
from megamarket.parsers.scrolling import MegamarketScrollPage
from megamarket.schemas.sellers import SellerImport
from megamarket.storage.report import ExcelReport
from megamarket.utils import ScrollCommand, parse_input_command


# Имя отчёта складывается из запросов и попадает и в папку, и в файл. Длинный
# перечень пришлось бы сворачивать уже файловой системе, поэтому сворачиваем
# сами и предсказуемо.
MAX_LABEL_LENGTH = 60


@dataclass(frozen=True, slots=True)
class ParseResult:
    queries: tuple[str, ...]
    # Сколько запросов дошло до конца: прогон могли прервать на середине,
    # и отчёт тогда неполон, о чём пользователю надо сказать.
    parsed_queries: int
    cards_count: int
    sellers_added: int
    output_path: Path


class ParserBrowserUnavailable(RuntimeError):
    pass


class InvalidParseCommand(ValueError):
    pass


def report_label(queries: Sequence[str]) -> str:
    """Как назвать общий отчёт по списку запросов."""
    label = "-".join(queries)
    if len(label) <= MAX_LABEL_LENGTH:
        return label
    return f"{queries[0][:MAX_LABEL_LENGTH]}-и-ещё-{len(queries) - 1}"


class ParserService:
    def __init__(self, remote: RemoteApiClient) -> None:
        self.remote = remote

    async def parse(self, commands: Sequence[str]) -> ParseResult:
        """Собрать выдачу по всем запросам и сложить её в один отчёт."""
        queries = self._read_queries(commands)

        browser = await self._connect_browser()
        cards: list[CardToPars] = []
        seen_links: set[str] = set()
        parsed_queries = 0
        page = None
        parser = None
        try:
            # Вкладка одна на все запросы: браузер у пользователя настоящий, и
            # плодить в нём окна на каждый запрос незачем.
            page = await browser.new_page()
            with collect_cdp_metrics(settings.cdp_metrics) as metrics:
                parser = MegamarketScrollPage(
                    page,
                    in_stock_only=True,
                    cdp_metrics=metrics,
                )
                for query in queries:
                    try:
                        found = await parser.parse(query)
                    except Exception as error:  # noqa: BLE001
                        # Собранное по прошлым запросам должно попасть в файл:
                        # ради него запуск и делали, терять его из-за сбоя на
                        # следующем запросе нельзя.
                        print(f"Запрос «{query}» прерван: {error}")
                        break
                    for card in found:
                        # Один товар попадает в выдачу нескольких запросов, а
                        # в общем файле ему место одно.
                        if card.card_link in seen_links:
                            continue
                        seen_links.add(card.card_link)
                        cards.append(card.model_copy(update={"query": query}))
                    parsed_queries += 1
                    if parser.interrupted:
                        # Вкладку закрыли или связь оборвалась: следующему
                        # запросу открывать выдачу уже негде.
                        break

        finally:
            if page is not None and (parser is None or not parser.interrupted):
                try:
                    await asyncio.wait_for(page.cdp.Page.close(), timeout=2)
                except (
                        TimeoutError,
                        ConnectionError,
                        ConnectionClosed,
                        ProtocolError,
                ):
                    pass
            try:
                await Target.close(browser)
            except (ConnectionError, ConnectionClosed, ProtocolError):
                pass

        imported = await self.remote.import_sellers([
            SellerImport(name=card.seller, link_to_card=card.card_link)
            for card in cards
        ])
        output_path = ExcelReport(
            cards,
            model=CardToPars,
            query=report_label(queries),
        ).save()
        return ParseResult(
            queries=tuple(queries),
            parsed_queries=parsed_queries,
            cards_count=len(cards),
            sellers_added=imported.added,
            output_path=output_path,
        )

    @staticmethod
    def _read_queries(commands: Sequence[str]) -> list[str]:
        """Разобрать весь список команд до подключения к браузеру.

        Опечатка в последнем запросе не должна обнаружиться через полчаса
        сбора, поэтому список проверяется целиком и заранее. Повторы
        отбрасываются: второй проход по той же выдаче ничего не добавит.
        """
        queries: list[str] = []
        seen: set[str] = set()
        for value in commands:
            try:
                command = parse_input_command(value)
            except ValueError as error:
                raise InvalidParseCommand(str(error)) from error
            if not isinstance(command, ScrollCommand):
                raise InvalidParseCommand(
                    "Ожидается команда формата scrolling||<запрос>"
                )
            key = command.query.casefold()
            if key in seen:
                continue
            seen.add(key)
            queries.append(command.query)
        if not queries:
            raise InvalidParseCommand("Укажите хотя бы один поисковый запрос")
        return queries

    @staticmethod
    async def _connect_browser() -> Browser:
        install_parsek_target_race_fix()
        try:
            return await asyncio.wait_for(
                connect_browser(settings.browser_endpoint),
                timeout=30,
            )
        except Exception as error:
            raise ParserBrowserUnavailable(
                f"Не удалось подключиться к браузеру: {settings.browser_endpoint}"
            ) from error
