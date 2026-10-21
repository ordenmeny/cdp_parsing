import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from megamarket.domain import CardToPars, Stock
from megamarket.storage.report import ExcelCardsReport, ExcelReport


class ExcelCardsReportTests(unittest.TestCase):
    @staticmethod
    def _cards() -> list[CardToPars]:
        return [
            CardToPars(
                title="Товар 1",
                price="100 ₽",
                seller="Продавец 1",
                card_link="https://megamarket.ru/product-1",
                stock=Stock.IN_STOCK,
            ),
            CardToPars(
                title="Товар 2",
                price="200 ₽",
                seller="Продавец 2",
                card_link="https://megamarket.ru/product-2",
                stock=Stock.IN_STOCK,
                seller_link="https://megamarket.ru/shop/already-filled/",
            ),
            CardToPars(
                title="Товар 3",
                price="",
                seller="Продавец 3",
                card_link="https://megamarket.ru/product-3",
                stock=Stock.OUT_OF_STOCK,
            ),
        ]

    def test_preserves_rows_and_existing_links(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "report.xlsx"
            ExcelReport(
                self._cards(),
                model=CardToPars,
                query="test",
            ).save(source)

            report = ExcelCardsReport(source)
            report.cards[0].seller_link = "https://megamarket.ru/shop/new-link/"
            report.cards[1].seller_link = "https://megamarket.ru/shop/changed/"
            output = report.save()

            self.assertEqual(
                output,
                Path(directory) / "report_with_seller_links.xlsx",
            )
            workbook = load_workbook(output)
            sheet = workbook[ExcelReport.SHEET_TITLE]
            headers = {
                cell.value: cell.column
                for cell in sheet[1]
                if cell.value is not None
            }
            seller_column = headers["Ссылка на продавца"]

            self.assertEqual(sheet.max_row, 4)
            self.assertEqual(
                sheet.cell(row=2, column=seller_column).value,
                "https://megamarket.ru/shop/new-link/",
            )
            self.assertEqual(
                sheet.cell(row=3, column=seller_column).value,
                "https://megamarket.ru/shop/already-filled/",
            )
            self.assertIsNone(sheet.cell(row=4, column=seller_column).value)

    def test_replaces_all_seller_details_from_database_values(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "report.xlsx"
            card = self._cards()[0].model_copy(update={
                "seller_link": "https://megamarket.ru/shop/old/",
                "official_name": "Старое юрлицо",
                "inn": "1111111111",
                "ogrn": "1111111111111",
                "seller_phone": "+7 111 111-11-11",
                "seller_email": "old@example.com",
            })
            ExcelReport([card], model=CardToPars, query="test").save(source)

            report = ExcelCardsReport(source)
            updated = report.cards[0]
            updated.seller_link = "https://megamarket.ru/shop/new/"
            updated.official_name = "Новое юрлицо"
            updated.inn = "2222222222"
            updated.ogrn = "2222222222222"
            updated.seller_phone = "+7 222 222-22-22"
            updated.seller_email = ""
            output = report.save(replace_seller_details=True)
            report.close()

            workbook = load_workbook(output)
            try:
                sheet = workbook[ExcelReport.SHEET_TITLE]
                headers = {
                    cell.value: cell.column
                    for cell in sheet[1]
                    if cell.value is not None
                }
                expected = {
                    "Ссылка на продавца": "https://megamarket.ru/shop/new/",
                    "Юр.\nЛицо": "Новое юрлицо",
                    "ИНН продавца": "2222222222",
                    "ОГРН": "2222222222222",
                    "seller_phone": "+7 222 222-22-22",
                    "seller_email": None,
                }
                for title, value in expected.items():
                    self.assertEqual(
                        sheet.cell(row=2, column=headers[title]).value,
                        value,
                    )
            finally:
                workbook.close()

    def test_old_legal_name_header_is_reused_and_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "report.xlsx"
            ExcelReport(self._cards()[:1], model=CardToPars, query="test").save(
                source
            )
            # Отчёт, снятый до переноса: заголовок юрлица в одну строку.
            workbook = load_workbook(source)
            sheet = workbook[ExcelReport.SHEET_TITLE]
            for cell in sheet[1]:
                if cell.value == "Юр.\nЛицо":
                    cell.value = "Юр. Лицо"
            workbook.save(source)
            workbook.close()

            report = ExcelCardsReport(source)
            report.cards[0].official_name = "Новое юрлицо"
            output = report.save(replace_seller_details=True)
            report.close()

            workbook = load_workbook(output)
            try:
                sheet = workbook[ExcelReport.SHEET_TITLE]
                headers = [cell.value for cell in sheet[1]]
                self.assertNotIn("Юр. Лицо", headers)
                # Колонка та же, а не дописанная в конец вторая.
                self.assertEqual(headers.count("Юр.\nЛицо"), 1)
                column = headers.index("Юр.\nЛицо") + 1
                self.assertTrue(sheet.cell(row=1, column=column).alignment.wrap_text)
                self.assertEqual(
                    sheet.cell(row=2, column=column).value,
                    "Новое юрлицо",
                )
            finally:
                workbook.close()

if __name__ == "__main__":
    unittest.main()
