import argparse
import asyncio
from pathlib import Path

from parsek_cdp import Browser

from megamarket.config import settings
from megamarket.cdp.parsek_compat import install_parsek_target_race_fix
from megamarket.parsers.parsing import MegamarketParseCard
from megamarket.storage.report import ExcelCardsReport


async def connect_browser(endpoint: str) -> Browser:
    install_parsek_target_race_fix()
    return await Browser.connect_http(endpoint)


async def set_seller_links(path: str | Path) -> Path:
    """Дополнить копию отчёта ссылками продавцов и вернуть путь результата."""
    report = ExcelCardsReport(path)
    print(f"Из отчёта загружено карточек: {len(report.cards)}")

    try:
        browser = await connect_browser(settings.browser_endpoint)
        parser = MegamarketParseCard(browser, report.cards)
        await parser.parse_all()
    finally:
        # Блокировка и другие сбои не должны уничтожить уже собранный результат.
        output_path = report.save()

    return output_path


def read_path() -> Path:
    argument_parser = argparse.ArgumentParser(
        description="Добавить ссылки продавцов в существующий отчёт Megamarket."
    )
    argument_parser.add_argument(
        "file",
        type=Path,
        nargs="?",
        help="Путь к отчёту .xlsx",
    )
    file = argument_parser.parse_args().file
    if file is not None:
        return file

    while True:
        entered = input("Путь к отчёту .xlsx: ").strip().strip('"')
        if entered:
            return Path(entered)


async def main() -> None:
    output_path = await set_seller_links(read_path())
    print(f"Готово: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
