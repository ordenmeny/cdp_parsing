import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from openpyxl import Workbook, load_workbook

from megamarket.domain import (
    CardToPars,
    product_id_from_link,
    seller_id_from_link,
)
from megamarket.parsers.scrolling import MegamarketScrollPage
from megamarket.storage.report import (
    ExcelCardsReport,
    ExcelReport,
    merge_excel_reports,
)


LINK = "https://megamarket.ru/catalog/details/smartfon-apple-100074688676_261094/"


def make_card(**fields) -> CardToPars:
    return CardToPars(
        **{
            "title": "Смартфон Apple iPhone 17 256Gb",
            "price": "95 450 ₽",
            "seller": "СОТОМАРКЕТ",
            "card_link": LINK,
            **fields,
        }
    )


class ProductIdTests(unittest.TestCase):
    def test_same_link_always_gives_the_same_id(self):
        self.assertEqual(product_id_from_link(LINK), product_id_from_link(LINK))
        # Пробелы по краям приходят из разметки и товара не меняют.
        self.assertEqual(product_id_from_link(f"  {LINK} "), product_id_from_link(LINK))

    def test_different_links_give_different_ids(self):
        other = "https://megamarket.ru/catalog/details/chehol-wiwu-600004746195_34438/"
        self.assertNotEqual(product_id_from_link(LINK), product_id_from_link(other))

    def test_id_is_a_positive_number_excel_keeps_exactly(self):
        value = product_id_from_link(LINK)
        self.assertIsInstance(value, int)
        self.assertGreater(value, 0)
        # У Excel точность целых заканчивается на 2^53.
        self.assertLess(value, 2 ** 53)

    def test_empty_link_has_no_id(self):
        self.assertEqual(product_id_from_link(""), 0)

    def test_no_collisions_on_a_realistic_number_of_cards(self):
        links = [
            f"https://megamarket.ru/catalog/details/tovar-{number}_{number % 900}/"
            for number in range(100_000)
        ]
        identifiers = {product_id_from_link(link) for link in links}
        self.assertEqual(len(identifiers), len(links))


class CardFieldsTests(unittest.TestCase):
    def test_id_is_filled_from_the_card_link(self):
        self.assertEqual(make_card().product_id, product_id_from_link(LINK))

    def test_explicitly_given_id_is_kept(self):
        self.assertEqual(make_card(product_id=42).product_id, 42)

    def test_seller_id_comes_from_the_card_link(self):
        self.assertEqual(make_card().seller_id, "261094")
        self.assertEqual(seller_id_from_link("не ссылка"), "")
        self.assertEqual(seller_id_from_link(""), "")

    def test_columns_that_are_never_filled_stay_empty(self):
        card = make_card()
        self.assertEqual(card.brand, "")
        self.assertEqual(card.legal_address, "")
        self.assertEqual(card.description, "")

    def test_brand_stays_empty_and_rating_is_optional(self):
        card = make_card()
        self.assertEqual(card.brand, "")
        self.assertEqual(card.rating, "")
        self.assertEqual(make_card(rating="4.9").rating, "4.9")


class ExtractedRatingTests(unittest.IsolatedAsyncioTestCase):
    async def test_rating_reaches_the_card(self):
        parser = MegamarketScrollPage(MagicMock())
        parser.page.evaluate = AsyncMock(
            return_value={
                "total": 2,
                "offset": 0,
                "items": [
                    {
                        "index": 0,
                        "title": "Смартфон Apple iPhone 17 256Gb",
                        "price": "95 450 ₽",
                        "rating": "4.9",
                        "seller": "СОТОМАРКЕТ",
                        "href": LINK,
                        "image": "",
                    },
                    {
                        "index": 1,
                        "title": "Чехол Wiwu Crystal",
                        "price": "990 ₽",
                        # У новых товаров рейтинга ещё нет.
                        "rating": "",
                        "seller": "TEXNO EDEM",
                        "href": "/catalog/details/chehol_34438/",
                        "image": "",
                    },
                ],
            }
        )

        cards = await parser.parse_current_page()

        self.assertEqual([card.rating for card in cards], ["4.9", ""])
        self.assertEqual([card.brand for card in cards], ["", ""])
        self.assertTrue(all(card.product_id > 0 for card in cards))


EXPECTED_COLUMNS = [
    "Ссылка",
    "Название товара",
    "Бренд",
    "ID карточки",
    "Описание товара",
    "Цены",
    "Рейтинг",
    "Продавец",
    "Ссылка на продавца",
    "ID продавца на маркетплейсе",
    "Юр. Лицо",
    "Юр. Адрес",
    "ИНН продавца",
    "ОГРН",
    "seller_phone",
    "seller_email",
    "link",
]


def sheet_of(path: Path):
    return load_workbook(path)[ExcelReport.SHEET_TITLE]


def column_of(sheet, title: str) -> int:
    for cell in sheet[1]:
        if cell.value == title:
            return cell.column
    raise AssertionError(f"колонки «{title}» нет в отчёте")


class ReportColumnsTests(unittest.TestCase):
    def test_columns_follow_the_agreed_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = ExcelReport(
                [make_card()],
                model=CardToPars,
                query="iphone 17",
            ).save(Path(directory) / "report.xlsx")

            headers = [cell.value for cell in sheet_of(path)[1]]

            self.assertEqual(headers[:len(EXPECTED_COLUMNS)], EXPECTED_COLUMNS)
            # Служебные колонки идут следом и порядок заданных не сдвигают.
            self.assertEqual(headers[len(EXPECTED_COLUMNS):], ["Наличие", "Запрос"])

    def test_id_is_written_as_text_and_read_back(self):
        card = make_card(rating="4.9")
        with tempfile.TemporaryDirectory() as directory:
            path = ExcelReport(
                [card],
                model=CardToPars,
                query="iphone 17",
            ).save(Path(directory) / "report.xlsx")

            sheet = sheet_of(path)
            cell = sheet.cell(row=2, column=column_of(sheet, "ID карточки"))
            # Клетка текстовая: числом Excel показал бы пятнадцать цифр как
            # 1,14492E+14 и округлил бы их при правке.
            self.assertEqual(cell.data_type, "s")
            self.assertEqual(cell.value, str(card.product_id))

            restored = ExcelCardsReport(path).cards
            self.assertEqual(restored[0].product_id, card.product_id)
            self.assertEqual(restored[0].rating, "4.9")
            self.assertEqual(restored[0].brand, "")

    def test_joined_report_keeps_the_id_as_text(self):
        card = make_card()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = ExcelReport(
                [card],
                model=CardToPars,
                query="iphone 17",
            ).save(root / "source.xlsx")
            target = root / "joined.xlsx"

            merge_excel_reports([source, source], target)

            sheet = sheet_of(target)
            cell = sheet.cell(row=2, column=column_of(sheet, "ID карточки"))
            self.assertEqual(cell.data_type, "s")
            self.assertEqual(cell.value, str(card.product_id))

    def test_report_with_old_column_names_is_still_readable(self):
        # Файлы, снятые до переименования колонок, открывает проверка продавцов.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = ExcelReport.SHEET_TITLE
            sheet.append(["Название", "Цена", "Продавец", "Ссылка на карточку"])
            sheet.append(["Смартфон", "95 450 ₽", "СОТОМАРКЕТ", LINK])
            workbook.save(path)

            cards = ExcelCardsReport(path).cards

            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].title, "Смартфон")
            self.assertEqual(cards[0].card_link, LINK)
            # Идентификаторы досчитываются из ссылки, даже если колонок не было.
            self.assertEqual(cards[0].product_id, product_id_from_link(LINK))
            self.assertEqual(cards[0].seller_id, "261094")


if __name__ == "__main__":
    unittest.main()
