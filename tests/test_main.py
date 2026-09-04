import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from megamarket.domain import CardToPars, Stock
from main import main
from megamarket.utils import ParseCommand


class _FakePageDomain:
    def __init__(self) -> None:
        self.close = AsyncMock()


class _FakePage:
    def __init__(self) -> None:
        self.cdp = MagicMock()
        self.cdp.Page = _FakePageDomain()


class _FakeBrowser:
    def __init__(self) -> None:
        self.pages: list[_FakePage] = []

    async def new_page(self):
        page = _FakePage()
        self.pages.append(page)
        return page


class MainTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _card(number: int) -> CardToPars:
        return CardToPars(
            title=f"Товар {number}",
            price=f"{number}00 ₽",
            seller=f"Продавец {number}",
            card_link=f"https://megamarket.ru/product-{number}",
            stock=Stock.IN_STOCK,
        )

    async def test_saves_all_parsed_cards_once(self):
        first, second = (self._card(number) for number in range(1, 3))
        first.card_link = (
            "https://megamarket.ru/catalog/details/"
            "product-one-700000000001_101/"
        )
        second.card_link = (
            "https://megamarket.ru/catalog/details/"
            "product-two-700000000002_102/"
        )
        output_path = Path("output/report.xlsx")
        all_stock_parser = MagicMock()
        all_stock_parser.parse = AsyncMock(return_value=[first, second])
        all_stock_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = output_path
        browser = _FakeBrowser()

        with (
            patch("main.connect_browser", new=AsyncMock(return_value=browser)),
            patch(
                "main.utils.read_command",
                return_value=ParseCommand(query="товар"),
            ),
            patch(
                "main.MegamarketParsePage",
                return_value=all_stock_parser,
            ) as parser_class,
            patch("main.ExcelReport", return_value=report) as report_class,
            patch("main.print_cards") as print_cards,
        ):
            await main()

        parser_class.assert_called_once_with(
            browser.pages[0],
            in_stock_only=True,
            start_page=1,
            cdp_metrics=None,
        )
        self.assertEqual(len(browser.pages), 1)
        browser.pages[0].cdp.Page.close.assert_awaited_once_with()
        all_stock_parser.parse.assert_awaited_once_with("товар")
        report_class.assert_called_once_with(
            [first, second],
            model=CardToPars,
            query="товар",
        )
        report.save.assert_called_once_with()
        print_cards.assert_not_called()

    async def test_manual_search_tab_close_saves_cards(self):
        card = self._card(1)
        parser = MagicMock()
        parser.parse = AsyncMock(return_value=[card])
        parser.interrupted = True
        report = MagicMock()
        report.save.return_value = Path("output/report.xlsx")
        browser = _FakeBrowser()

        with (
            patch("main.connect_browser", new=AsyncMock(return_value=browser)),
            patch(
                "main.utils.read_command",
                return_value=ParseCommand(query="товар"),
            ),
            patch("main.MegamarketParsePage", return_value=parser),
            patch("main.ExcelReport", return_value=report),
        ):
            await main()

        report.save.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
