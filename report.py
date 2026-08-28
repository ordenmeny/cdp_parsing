import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from domain import CardToPars


class ExcelReport:
    """Отчёт по собранным карточкам в xlsx."""

    SHEET_TITLE = "Карточки"
    # заголовок столбца и его ширина
    COLUMNS = (
        ("Название", 60),
        ("Цена, ₽", 14),
        ("В наличии", 11),
        ("Продавец", 30),
        ("Ссылка на карточку", 50),
        ("Ссылка на продавца", 40),
    )
    PRICE_FORMAT = "# ##0"
    HEADER_FILL = "DCE6F1"
    LINK_COLOR = "0563C1"

    def __init__(self, cards: Sequence[CardToPars], *, query: str = "") -> None:
        self.cards = cards
        self.query = query

    @classmethod
    def _price_number(cls, price: str) -> float | None:
        """Цену пишем числом, чтобы по ней можно было сортировать и считать."""
        digits = re.sub(r"[^\d,.]", "", price).replace(",", ".")
        try:
            return float(digits)
        except ValueError:
            return None

    def _default_path(self) -> Path:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        query = re.sub(r"[^\w-]+", "_", self.query).strip("_")
        name = f"megamarket_{query}_{stamp}" if query else f"megamarket_{stamp}"
        return Path(f"{name}.xlsx")

    def _write_header(self, sheet: Worksheet) -> None:
        font = Font(bold=True)
        fill = PatternFill("solid", fgColor=self.HEADER_FILL)
        for number, (title, width) in enumerate(self.COLUMNS, start=1):
            cell = sheet.cell(row=1, column=number, value=title)
            cell.font = font
            cell.fill = fill
            cell.alignment = Alignment(vertical="center")
            sheet.column_dimensions[get_column_letter(number)].width = width

    def _write_link(self, sheet: Worksheet, row: int, column: int, url: str) -> None:
        if not url:
            return
        cell = sheet.cell(row=row, column=column, value=url)
        cell.hyperlink = url
        cell.font = Font(color=self.LINK_COLOR, underline="single")

    def _write_card(self, sheet: Worksheet, row: int, card: CardToPars) -> None:
        sheet.cell(row=row, column=1, value=card.title)

        price = self._price_number(card.price)
        cell = sheet.cell(row=row, column=2, value=price if price is not None else card.price)
        if price is not None:
            cell.number_format = self.PRICE_FORMAT

        sheet.cell(row=row, column=3, value="да" if card.in_stock else "нет")
        sheet.cell(row=row, column=4, value=card.seller)
        self._write_link(sheet, row, 5, card.card_link)
        self._write_link(sheet, row, 6, card.seller_link)

    def _finish(self, sheet: Worksheet) -> None:
        last_row = len(self.cards) + 1
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(self.COLUMNS))}{last_row}"

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self._default_path()

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = self.SHEET_TITLE

        self._write_header(sheet)
        for number, card in enumerate(self.cards, start=2):
            self._write_card(sheet, number, card)
        self._finish(sheet)

        workbook.save(target)
        print(f"Отчёт сохранён: {target.resolve()} (строк: {len(self.cards)})")
        return target
