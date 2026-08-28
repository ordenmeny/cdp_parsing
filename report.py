import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from pydantic import BaseModel

from config import settings


class ExcelReport:
    SHEET_TITLE = "Карточки"
    MAX_WIDTH = 90

    def __init__(
            self,
            rows: Sequence[BaseModel],
            *,
            model: type[BaseModel],
            query: str = "",
    ) -> None:
        self.rows = rows
        self.model = model
        self.query = query

    @staticmethod
    def _text(value) -> str:
        """В отчёте всё строками: сортировать и считать в нём нечего."""
        if isinstance(value, bool):
            return "да" if value else "нет"
        if value is None:
            return ""
        return str(value)

    def _default_path(self) -> Path:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        query = re.sub(r"[^\w-]+", "_", self.query).strip("_")
        name = f"megamarket_{query}_{stamp}" if query else f"megamarket_{stamp}"
        return settings.report_dir / f"{name}.xlsx"

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self._default_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = self.SHEET_TITLE

        # колонки - поля модели в порядке объявления
        columns = self.model.model_fields

        for number, (name, column) in enumerate(columns.items(), start=1):
            cell = sheet.cell(row=1, column=number)
            cell.value = column.title or name
            cell.font = Font(bold=True)

        for row, item in enumerate(self.rows, start=2):
            for number, name in enumerate(columns, start=1):
                value = self._text(getattr(item, name))
                sheet.cell(row=row, column=number, value=value)

        for number in range(1, len(columns) + 1):
            letter = get_column_letter(number)
            longest = max(len(str(cell.value or "")) for cell in sheet[letter])
            sheet.column_dimensions[letter].width = min(longest + 2, self.MAX_WIDTH)

        sheet.freeze_panes = "A2"
        last_column = get_column_letter(len(columns))
        sheet.auto_filter.ref = f"A1:{last_column}{len(self.rows) + 1}"

        workbook.save(target)
        print(f"Отчёт сохранён: {target.resolve()} (строк: {len(self.rows)})")
        return target
