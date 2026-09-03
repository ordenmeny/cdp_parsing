import asyncio

from parsek_cdp import Browser, ProtocolError
from websockets.exceptions import ConnectionClosed

from megamarket import utils
from megamarket.cdp.cdp_metrics import collect_cdp_metrics
from megamarket.config import settings
from megamarket.domain import CardToPars, Stock
from megamarket.cdp.parsek_compat import install_parsek_target_race_fix
from megamarket.parsers.parsing import (
    MegamarketParseCard,
    MegamarketParsePage,
)
from megamarket.storage.report import ExcelReport, join_excel_reports
from megamarket.parsers.scrolling import MegamarketScrollPage
from megamarket.utils import print_cards


async def connect_browser(endpoint: str) -> Browser:
    install_parsek_target_race_fix()
    print(f"Подключаемся к браузеру: {endpoint}...")
    try:
        browser = await asyncio.wait_for(
            Browser.connect_http(endpoint),
            timeout=30,
        )
    except TimeoutError as error:
        raise RuntimeError(
            f"Не удалось подключиться к браузеру по адресу {endpoint} "
            "за 30 секунд."
        ) from error
    print("Подключение к браузеру установлено.")
    return browser


def build_parser(
        page,
        command: utils.InputCommand,
        metrics,
) -> MegamarketParsePage:
    """Выбрать поток сбора по введённой команде.

    Потоки не смешиваются: ``scrolling||запрос`` набирает выдачу догрузкой в
    одном документе, обычный запрос — обходом страниц ``page-N``.
    """
    if isinstance(command, utils.ScrollCommand):
        return MegamarketScrollPage(
            page,
            in_stock_only=True,
            cdp_metrics=metrics,
        )
    return MegamarketParsePage(
        page,
        in_stock_only=True,
        start_page=command.start_page,
        cdp_metrics=metrics,
    )


async def main() -> None:
    command = utils.read_command()
    if isinstance(command, utils.JoinCommand):
        join_excel_reports(command.directory)
        return

    browser = await connect_browser(settings.browser_endpoint)
    try:
        query = command.query

        print("Создаём вкладку для парсинга...")
        page = await browser.new_page()
        print("Вкладка для парсинга создана.")
        # Парсер может не создаться: тогда закрывать вкладку всё равно надо,
        # а спрашивать у несуществующего объекта про прерывание — нет.
        in_stock_parser = None
        try:
            with collect_cdp_metrics(settings.cdp_metrics) as metrics:
                in_stock_parser = build_parser(page, command, metrics)
                in_stock_cards = await in_stock_parser.parse(query)
        finally:
            if in_stock_parser is None or not in_stock_parser.interrupted:
                try:
                    await asyncio.wait_for(page.cdp.Page.close(), timeout=2)
                except (
                        TimeoutError,
                        ConnectionError,
                        ConnectionClosed,
                        ProtocolError,
                ):
                    pass

        report = ExcelReport(
            in_stock_cards,
            model=CardToPars,
            query=query,
        )
        output_path = report.save()

        # Колонка со ссылкой продавца остаётся пустой: слагификатор её
        # угадывал, а проверять догадки пока некому.

        # print_cards(in_stock_cards)

    finally:
        pass


if __name__ == "__main__":
    asyncio.run(main())
