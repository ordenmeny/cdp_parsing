import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from megamarket.db.models import Sellers
from megamarket.domain import CardToPars, SellerStatus
from megamarket.schemas.sellers import SellerUpdate
from megamarket.services.parser import ParserService
from megamarket.services.sellers import SellerService


class SellerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_updates_seller_by_id(self):
        seller = Sellers(
            seller_id="147929",
            name="Инструмент Сибири",
            link_to_seller="https://megamarket.ru/shop/instrument-sibiri/",
            link_to_card="https://megamarket.ru/catalog/details/item_147929/",
            status=SellerStatus.UNCONFIRMED,
        )
        repository = MagicMock()
        repository.get_by_identity = AsyncMock(return_value=seller)
        repository.flush = AsyncMock()
        repository.commit = AsyncMock()
        repository.rollback = AsyncMock()

        result = await SellerService(repository).set_sellers([
            SellerUpdate(seller_id="147929", status=SellerStatus.CORRECT),
        ])

        self.assertEqual(result, [seller])
        self.assertIs(seller.status, SellerStatus.CORRECT)
        repository.commit.assert_awaited_once_with()
        repository.rollback.assert_not_awaited()


class ParserServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_scrolling_parser_and_saves_report(self):
        card = CardToPars(
            title="Товар",
            price="100 ₽",
            seller="Продавец",
            card_link=(
                "https://megamarket.ru/catalog/details/"
                "product-100000000001_147929/"
            ),
        )
        page = MagicMock()
        page.cdp.Page.close = AsyncMock()
        browser = MagicMock()
        browser.new_page = AsyncMock(return_value=page)
        scrolling_parser = MagicMock()
        scrolling_parser.parse = AsyncMock(return_value=[card])
        scrolling_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")

        with (
            patch.object(
                ParserService,
                "_connect_browser",
                new=AsyncMock(return_value=browser),
            ),
            patch(
                "megamarket.services.parser.MegamarketScrollPage",
                return_value=scrolling_parser,
            ),
            patch(
                "megamarket.services.parser.ExcelReport",
                return_value=report,
            ) as report_class,
            patch(
                "megamarket.services.parser.Target.close",
                new=AsyncMock(),
            ),
        ):
            result = await ParserService().parse("scrolling||makita")

        scrolling_parser.parse.assert_awaited_once_with("makita")
        report_class.assert_called_once_with(
            [card],
            model=CardToPars,
            query="makita",
        )
        report.save.assert_called_once_with()
        page.cdp.Page.close.assert_awaited_once_with()
        self.assertEqual(result.cards_count, 1)
        self.assertEqual(result.output_path, Path("output/result.xlsx"))

    async def test_rejects_non_scrolling_command_before_opening_browser(self):
        with patch.object(
                ParserService,
                "_connect_browser",
                new=AsyncMock(),
        ) as connect:
            with self.assertRaisesRegex(ValueError, "scrolling"):
                await ParserService().parse("makita")

        connect.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
