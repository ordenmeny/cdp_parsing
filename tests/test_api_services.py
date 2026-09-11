import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from megamarket.db.models import Sellers
from megamarket.domain import CardToPars, SellerInfo, SellerStatus
from megamarket.repositories.sellers import SellerRepository
from megamarket.schemas.sellers import (
    SellerImport,
    SellerResponse,
    SellersImportResponse,
    SellerUpdate,
)
from megamarket.services.parser import ParserService, report_label
from megamarket.services.sellers import SellerService


class SellerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_adds_parsed_seller_as_unconfirmed(self):
        repository = MagicMock()
        repository.add_new = AsyncMock(return_value=1)
        repository.commit = AsyncMock()
        repository.rollback = AsyncMock()

        added = await SellerService(repository).add_new([
            SellerImport(
                name="  Кувалда.ру  ",
                link_to_card=(
                    "https://megamarket.ru/catalog/details/"
                    "instrument-100000000001_147929/"
                ),
            )
        ])

        self.assertEqual(added, 1)
        candidates = repository.add_new.await_args.args[0]
        self.assertEqual(len(candidates), 1)
        seller = candidates[0]
        self.assertEqual(seller.seller_id, "147929")
        self.assertEqual(seller.name, "Кувалда.ру")
        self.assertEqual(
            seller.link_to_seller,
            "https://megamarket.ru/shop/kuvaldaru/",
        )
        self.assertIs(seller.status, SellerStatus.UNCONFIRMED)
        repository.commit.assert_awaited_once_with()
        repository.rollback.assert_not_awaited()

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


class SellerRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_recheck_fields_do_not_erase_collected_data(self):
        seller = Sellers(
            seller_id="147929",
            name="embeq.store",
            link_to_seller="https://megamarket.ru/shop/embeq-store/",
            link_to_card="https://megamarket.ru/card_147929/",
            status=SellerStatus.INCORRECT,
            email="old@example.com",
            ogrn="1234567890123",
            official_name="Старое официальное название",
            inn="1234567890",
            phone="+7 900 000-00-00",
            rating=4.8,
        )
        session = MagicMock()
        session.get = AsyncMock(return_value=seller)
        session.flush = AsyncMock()

        await SellerRepository(session).confirm(
            seller.seller_id,
            SellerInfo(
                seller_id=seller.seller_id,
                name=seller.name,
                official_name="Новое официальное название",
            ),
            "https://megamarket.ru/shop/embeqstore/",
        )

        self.assertEqual(
            seller.link_to_seller,
            "https://megamarket.ru/shop/embeqstore/",
        )
        self.assertEqual(seller.email, "old@example.com")
        self.assertEqual(seller.ogrn, "1234567890123")
        self.assertEqual(seller.official_name, "Новое официальное название")
        self.assertEqual(seller.inn, "1234567890")
        self.assertEqual(seller.phone, "+7 900 000-00-00")
        self.assertEqual(seller.rating, 4.8)
        self.assertIs(seller.status, SellerStatus.CORRECT)
        session.flush.assert_awaited_once_with()


class ReportLabelTests(unittest.TestCase):
    def test_single_query_names_the_report_as_before(self):
        self.assertEqual(report_label(["makita"]), "makita")

    def test_queries_are_listed_while_the_name_stays_short(self):
        self.assertEqual(
            report_label(["makita", "iphone 17", "samsung s24"]),
            "makita-iphone 17-samsung s24",
        )

    def test_long_list_is_folded_instead_of_growing_the_path(self):
        queries = [f"запрос номер {number}" for number in range(1, 11)]
        self.assertEqual(report_label(queries), "запрос номер 1-и-ещё-9")


class ParserServiceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _card(title: str, number: int, query: str = "") -> CardToPars:
        return CardToPars(
            title=title,
            price="100 ₽",
            seller=f"Продавец {number}",
            card_link=(
                "https://megamarket.ru/catalog/details/"
                f"product-10000000000{number}_147929/"
            ),
            query=query,
        )

    @staticmethod
    def _browser(page):
        browser = MagicMock()
        browser.new_page = AsyncMock(return_value=page)
        return browser

    @staticmethod
    def _page():
        page = MagicMock()
        page.cdp.Page.close = AsyncMock()
        return page

    @staticmethod
    def _remote(added: int = 1, sellers=()):
        remote = MagicMock()
        remote.import_sellers = AsyncMock(
            return_value=SellersImportResponse(added=added)
        )
        remote.get_sellers = AsyncMock(return_value=list(sellers))
        return remote

    @staticmethod
    def _running(browser, parser, report):
        """Патчи, за которыми остаётся только логика сервиса."""
        return (
            patch.object(
                ParserService,
                "_connect_browser",
                new=AsyncMock(return_value=browser),
            ),
            patch(
                "megamarket.services.parser.MegamarketScrollPage",
                return_value=parser,
            ),
            patch(
                "megamarket.services.parser.ExcelReport",
                return_value=report,
            ),
            patch(
                "megamarket.services.parser.Target.close",
                new=AsyncMock(),
            ),
        )

    async def test_runs_scrolling_parser_and_saves_report(self):
        card = self._card("Товар", 1)
        page = self._page()
        scrolling_parser = MagicMock()
        scrolling_parser.parse = AsyncMock(return_value=[card])
        scrolling_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")
        remote = self._remote()

        connect, page_class, report_class, target = self._running(
            self._browser(page),
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class as report_factory, target:
            result = await ParserService(remote).parse(["scrolling||makita"])

        scrolling_parser.parse.assert_awaited_once_with("makita")
        report_factory.assert_called_once_with(
            [self._card("Товар", 1, query="makita")],
            model=CardToPars,
            query="makita",
        )
        report.save.assert_called_once_with()
        remote.import_sellers.assert_awaited_once()
        imported = remote.import_sellers.await_args.args[0]
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0].name, "Продавец 1")
        self.assertEqual(imported[0].link_to_card, card.card_link)
        page.cdp.Page.close.assert_awaited_once_with()
        self.assertEqual(result.queries, ("makita",))
        self.assertEqual(result.cards_count, 1)
        self.assertEqual(result.sellers_added, 1)
        self.assertEqual(result.output_path, Path("output/result.xlsx"))

    @staticmethod
    def _seller(status=SellerStatus.CORRECT):
        return SellerResponse(
            seller_id="147929",
            name="Продавец 1",
            link_to_seller="https://megamarket.ru/shop/prodavec/",
            link_to_card="https://megamarket.ru/catalog/details/x_147929/",
            status=status,
            email="shop@example.com",
            ogrn="1234567890123",
            official_name="ООО «Продавец»",
            inn="1234567890",
            phone="+7 900 000-00-00",
            rating=4.8,
        )

    async def test_seller_details_come_from_the_database(self):
        card = self._card("Товар", 1)
        page = self._page()
        scrolling_parser = MagicMock()
        scrolling_parser.parse = AsyncMock(return_value=[card])
        scrolling_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")
        remote = self._remote(sellers=[self._seller()])

        connect, page_class, report_class, target = self._running(
            self._browser(page),
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class as report_factory, target:
            await ParserService(remote).parse(["scrolling||makita"])

        row = report_factory.call_args.args[0][0]
        self.assertEqual(row.seller_id, "147929")
        self.assertEqual(row.official_name, "ООО «Продавец»")
        self.assertEqual(row.inn, "1234567890")
        self.assertEqual(row.ogrn, "1234567890123")
        self.assertEqual(row.seller_phone, "+7 900 000-00-00")
        self.assertEqual(row.seller_email, "shop@example.com")
        self.assertEqual(row.seller_link, "https://megamarket.ru/shop/prodavec/")
        # Эти колонки не заполняет никто.
        self.assertEqual((row.brand, row.legal_address, row.description), ("", "", ""))

    async def test_unchecked_seller_leaves_the_link_alone(self):
        card = self._card("Товар", 1)
        page = self._page()
        scrolling_parser = MagicMock()
        scrolling_parser.parse = AsyncMock(return_value=[card])
        scrolling_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")
        remote = self._remote(sellers=[self._seller(SellerStatus.UNCONFIRMED)])

        connect, page_class, report_class, target = self._running(
            self._browser(page),
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class as report_factory, target:
            await ParserService(remote).parse(["scrolling||makita"])

        row = report_factory.call_args.args[0][0]
        # Реквизиты подставились, а ссылка — нет: она ещё догадка.
        self.assertEqual(row.inn, "1234567890")
        self.assertEqual(row.seller_link, "")

    async def test_report_survives_a_database_that_did_not_answer(self):
        card = self._card("Товар", 1)
        page = self._page()
        scrolling_parser = MagicMock()
        scrolling_parser.parse = AsyncMock(return_value=[card])
        scrolling_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")
        remote = self._remote()
        remote.get_sellers = AsyncMock(side_effect=RuntimeError("нет связи"))

        connect, page_class, report_class, target = self._running(
            self._browser(page),
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class as report_factory, target:
            result = await ParserService(remote).parse(["scrolling||makita"])

        # Файл важнее реквизитов: он всё равно сохраняется.
        report.save.assert_called_once_with()
        self.assertEqual(result.cards_count, 1)
        self.assertEqual(report_factory.call_args.args[0][0].inn, "")

    async def test_every_query_lands_in_a_single_report(self):
        found = {
            "makita": [self._card("Шуруповёрт", 1)],
            "iphone 17": [self._card("Смартфон", 2)],
            "samsung s24": [self._card("Смартфон Samsung", 3)],
        }
        page = self._page()
        browser = self._browser(page)
        scrolling_parser = MagicMock()
        scrolling_parser.parse = AsyncMock(side_effect=lambda query: found[query])
        scrolling_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")
        remote = self._remote(added=3)

        connect, page_class, report_class, target = self._running(
            browser,
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class as report_factory, target:
            result = await ParserService(remote).parse([
                "scrolling||makita",
                "scrolling||iphone 17",
                "scrolling||samsung s24",
            ])

        self.assertEqual(
            [call.args[0] for call in scrolling_parser.parse.await_args_list],
            ["makita", "iphone 17", "samsung s24"],
        )
        # Вкладка одна на все запросы, отчёт — тоже один.
        browser.new_page.assert_awaited_once_with()
        report_factory.assert_called_once_with(
            [
                self._card("Шуруповёрт", 1, query="makita"),
                self._card("Смартфон", 2, query="iphone 17"),
                self._card("Смартфон Samsung", 3, query="samsung s24"),
            ],
            model=CardToPars,
            query="makita-iphone 17-samsung s24",
        )
        report.save.assert_called_once_with()
        remote.import_sellers.assert_awaited_once()
        self.assertEqual(len(remote.import_sellers.await_args.args[0]), 3)
        self.assertEqual(result.queries, ("makita", "iphone 17", "samsung s24"))
        self.assertEqual(result.cards_count, 3)

    async def test_broken_second_query_keeps_the_first_one(self):
        collected = self._card("Шуруповёрт", 1)
        page = self._page()
        scrolling_parser = MagicMock()
        scrolling_parser.interrupted = False

        async def parse_then_break(query: str):
            if query == "makita":
                return [collected]
            raise RuntimeError("вкладка отвалилась")

        scrolling_parser.parse = AsyncMock(side_effect=parse_then_break)
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")

        connect, page_class, report_class, target = self._running(
            self._browser(page),
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class as report_factory, target:
            result = await ParserService(self._remote()).parse([
                "scrolling||makita",
                "scrolling||iphone 17",
            ])

        # Сбой на втором запросе не должен уносить с собой первый.
        self.assertEqual(
            [row.query for row in report_factory.call_args.args[0]],
            ["makita"],
        )
        report.save.assert_called_once_with()
        self.assertEqual(result.cards_count, 1)
        self.assertEqual(result.parsed_queries, 1)
        self.assertEqual(len(result.queries), 2)

    async def test_card_found_by_two_queries_is_written_once(self):
        shared = self._card("Шуруповёрт", 1)
        page = self._page()
        scrolling_parser = MagicMock()
        scrolling_parser.parse = AsyncMock(return_value=[shared])
        scrolling_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")

        connect, page_class, report_class, target = self._running(
            self._browser(page),
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class as report_factory, target:
            result = await ParserService(self._remote()).parse([
                "scrolling||makita",
                "scrolling||шуруповёрт makita",
            ])

        rows = report_factory.call_args.args[0]
        self.assertEqual(len(rows), 1)
        # Строка остаётся за тем запросом, который нашёл её первым.
        self.assertEqual(rows[0].query, "makita")
        self.assertEqual(result.cards_count, 1)

    async def test_repeated_query_is_parsed_once(self):
        page = self._page()
        scrolling_parser = MagicMock()
        scrolling_parser.parse = AsyncMock(return_value=[])
        scrolling_parser.interrupted = False
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")

        connect, page_class, report_class, target = self._running(
            self._browser(page),
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class, target:
            result = await ParserService(self._remote(added=0)).parse([
                "scrolling||makita",
                "scrolling||Makita",
            ])

        scrolling_parser.parse.assert_awaited_once_with("makita")
        self.assertEqual(result.queries, ("makita",))

    async def test_closed_tab_stops_the_remaining_queries(self):
        collected = self._card("Шуруповёрт", 1)
        page = self._page()
        scrolling_parser = MagicMock()
        scrolling_parser.interrupted = False

        async def parse_and_lose_the_tab(query: str) -> list[CardToPars]:
            scrolling_parser.interrupted = True
            return [collected]

        scrolling_parser.parse = AsyncMock(side_effect=parse_and_lose_the_tab)
        report = MagicMock()
        report.save.return_value = Path("output/result.xlsx")

        connect, page_class, report_class, target = self._running(
            self._browser(page),
            scrolling_parser,
            report,
        )
        with connect, page_class, report_class as report_factory, target:
            result = await ParserService(self._remote()).parse([
                "scrolling||makita",
                "scrolling||iphone 17",
            ])

        scrolling_parser.parse.assert_awaited_once_with("makita")
        # Собранное до обрыва всё равно попадает в файл.
        self.assertEqual(len(report_factory.call_args.args[0]), 1)
        self.assertEqual(result.cards_count, 1)
        page.cdp.Page.close.assert_not_awaited()

    async def test_rejects_non_scrolling_command_before_opening_browser(self):
        with patch.object(
                ParserService,
                "_connect_browser",
                new=AsyncMock(),
        ) as connect:
            with self.assertRaisesRegex(ValueError, "scrolling"):
                await ParserService(MagicMock()).parse(["makita"])

        connect.assert_not_awaited()

    async def test_rejects_a_bad_command_anywhere_in_the_list(self):
        with patch.object(
                ParserService,
                "_connect_browser",
                new=AsyncMock(),
        ) as connect:
            with self.assertRaisesRegex(ValueError, "scrolling"):
                await ParserService(MagicMock()).parse([
                    "scrolling||makita",
                    "iphone 17",
                ])

        connect.assert_not_awaited()

    async def test_rejects_an_empty_list_of_commands(self):
        with patch.object(
                ParserService,
                "_connect_browser",
                new=AsyncMock(),
        ) as connect:
            with self.assertRaises(ValueError):
                await ParserService(MagicMock()).parse([])

        connect.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
