import re
from copy import copy
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from pydantic import BaseModel

from megamarket.config import settings
from megamarket.domain import CardToPars


# Колонки переименовывались, а проверка продавцов читает отчёты по названиям.
# Старые файлы должны открываться по-прежнему, поэтому прежние заголовки
# остаются понятными.
LEGACY_TITLES = {
    "Название": "title",
    "Цена": "price",
    "Ссылка на карточку": "card_link",
    "Ссылка на изображение": "image_link",
    "ID товара": "product_id",
}


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
        """В отчёте всё строками: сортировать и считать в нём нечего.

        Идентификатор товара — тоже: он из пятнадцати цифр, и числом Excel
        показал бы его как 1,14492E+14, а при правке округлил бы.
        """
        if isinstance(value, bool):
            return "да" if value else "нет"
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _safe_name(value: str, fallback: str) -> str:
        return re.sub(r"[^\w-]+", "_", value).strip("_") or fallback

    @classmethod
    def _site_name(cls) -> str:
        host = urlsplit(settings.base_url).hostname or "site"
        host = host.removeprefix("www.")
        return cls._safe_name(host.split(".")[0], "site")

    def _default_path(self) -> Path:
        # Микросекунды гарантируют отдельное имя даже при быстром перезапуске.
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
        query = self._safe_name(self.query, "query")
        directory = settings.report_dir / f"{self._site_name()}-{query}"
        return directory / f"{stamp}-{query}.xlsx"

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


def report_sheet(workbook):
    """Лист с карточками: у наших отчётов он назван, у чужих берём первый."""
    if ExcelReport.SHEET_TITLE in workbook.sheetnames:
        return workbook[ExcelReport.SHEET_TITLE]
    return workbook.active


def read_headers(path: Path) -> list[str]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        rows = report_sheet(workbook).iter_rows(values_only=True)
        return [str(value or "") for value in next(rows, ())]
    finally:
        workbook.close()


def joined_report_filename() -> str:
    """Имя файла для объединения, снятого прямо сейчас."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    return f"all-{ExcelReport._site_name()}-{stamp}.xlsx"


def merge_excel_reports(sources: Sequence[Path], target: Path) -> int:
    """Сложить строки нескольких отчётов в один файл; вернуть число строк.

    Колонки сопоставляются по названию, а не по номеру: в одно объединение
    попадают и отчёты, снятые до появления новой колонки, — недостающие клетки
    остаются пустыми. Строки на повторы не проверяются: объединение должно быть
    быстрым, а что считать дублем, зависит от задачи.
    """
    columns: list[str] = []
    positions: dict[str, int] = {}
    for path in sources:
        for header in read_headers(path):
            if header and header not in positions:
                positions[header] = len(columns)
                columns.append(header)
    if not columns:
        raise ValueError("В выбранных файлах отсутствуют заголовки таблицы.")

    result = Workbook()
    sheet = result.active
    sheet.title = ExcelReport.SHEET_TITLE
    sheet.append(columns)
    # Ширины набираем по ходу записи: отдельный проход по готовому листу стоил
    # бы столько же, сколько само объединение.
    widths = [len(header) for header in columns]
    written = 0

    for path in sources:
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            rows = report_sheet(workbook).iter_rows(values_only=True)
            headers = [str(value or "") for value in next(rows, ())]
            if not any(headers):
                continue
            places = [positions.get(header) for header in headers]
            for values in rows:
                if not any(value not in (None, "") for value in values):
                    continue
                row: list = [None] * len(columns)
                for place, value in zip(places, values):
                    if place is None:
                        continue
                    row[place] = value
                    widths[place] = max(widths[place], len(str(value or "")))
                sheet.append(row)
                written += 1
        finally:
            workbook.close()

    for number, width in enumerate(widths, start=1):
        cell = sheet.cell(row=1, column=number)
        cell.font = Font(bold=True)
        sheet.column_dimensions[get_column_letter(number)].width = min(
            width + 2,
            ExcelReport.MAX_WIDTH,
        )
    sheet.freeze_panes = "A2"
    last_column = get_column_letter(len(columns))
    sheet.auto_filter.ref = f"A1:{last_column}{written + 1}"

    target.parent.mkdir(parents=True, exist_ok=True)
    result.save(target)
    return written


def join_excel_reports(directory: str | Path) -> Path:
    """Объединить строки всех отчётов ``.xlsx`` в указанной папке."""
    source_dir = Path(directory).expanduser().resolve()
    if not source_dir.is_dir():
        raise NotADirectoryError(f"Папка с отчётами не найдена: {source_dir}")

    files = sorted(
        path
        for path in source_dir.glob("*.xlsx")
        if path.is_file()
        and not path.name.startswith(("all-", "~$"))
    )
    if not files:
        raise FileNotFoundError(f"В папке нет файлов .xlsx: {source_dir}")

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    site = ExcelReport._site_name()
    directory_prefix = f"{site}-"
    query = (
        source_dir.name[len(directory_prefix):]
        if source_dir.name.startswith(directory_prefix)
        else source_dir.name
    )
    output_path = source_dir / f"all-{site}{stamp}-{query}.xlsx"
    written = merge_excel_reports(files, output_path)
    print(
        f"Общий отчёт сохранён: {output_path} "
        f"(файлов: {len(files)}, строк: {written})"
    )
    return output_path


class ExcelCardsReport:
    """Существующий отчёт с привязкой объектов ``CardToPars`` к строкам."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Файл отчёта не найден: {self.path}")
        if self.path.suffix.casefold() != ".xlsx":
            raise ValueError("Ожидается файл с расширением .xlsx")

        self.workbook = load_workbook(self.path)
        self.sheet = self._get_cards_sheet()
        self._columns = self._read_columns()
        self._seller_link_column = self._ensure_seller_link_column()
        self._rows: list[tuple[int, CardToPars, str]] = []
        self.cards = self._read_cards()

    def _get_cards_sheet(self):
        return report_sheet(self.workbook)

    def _read_columns(self) -> dict[str, int]:
        columns: dict[str, int] = {}
        for cell in self.sheet[1]:
            if cell.value is not None:
                columns[str(cell.value).strip()] = cell.column
        return columns

    @staticmethod
    def _field_title(name: str) -> str:
        field = CardToPars.model_fields[name]
        return field.title or name

    def _ensure_seller_link_column(self) -> int:
        title = self._field_title("seller_link")
        existing = self._columns.get(title)
        if existing is not None:
            return existing

        column = self.sheet.max_column + 1
        cell = self.sheet.cell(row=1, column=column, value=title)
        if column > 1:
            previous = self.sheet.cell(row=1, column=column - 1)
            cell._style = copy(previous._style)
        else:
            cell.font = Font(bold=True)
        self._columns[title] = column
        return column

    def _column_for(self, name: str) -> int | None:
        """Номер колонки поля — по текущему заголовку или по прежнему."""
        column = self._columns.get(self._field_title(name))
        if column is not None:
            return column
        for legacy, field_name in LEGACY_TITLES.items():
            if field_name == name and legacy in self._columns:
                return self._columns[legacy]
        return None

    def _required_columns(self) -> dict[str, int]:
        """Найти доступные колонки и проверить обязательные поля модели.

        Поля со значением по умолчанию могут отсутствовать в старых отчётах.
        Это позволяет дополнять ссылками продавцов файлы, созданные до
        появления колонки со ссылкой на изображение.
        """
        result: dict[str, int] = {}
        missing: list[str] = []
        for name, field in CardToPars.model_fields.items():
            if name == "seller_link":
                continue
            column = self._column_for(name)
            if column is None:
                if field.is_required():
                    missing.append(self._field_title(name))
            else:
                result[name] = column
        if missing:
            raise ValueError(
                "В отчёте отсутствуют обязательные колонки: " + ", ".join(missing)
            )
        return result

    def _read_cards(self) -> list[CardToPars]:
        required = self._required_columns()
        cards: list[CardToPars] = []
        for row_number in range(2, self.sheet.max_row + 1):
            values = {
                name: self.sheet.cell(row=row_number, column=column).value
                for name, column in required.items()
            }
            if not any(value not in (None, "") for value in values.values()):
                continue

            data = {
                name: value
                for name, value in values.items()
                if value not in (None, "")
            }
            data["seller_link"] = (
                    self.sheet.cell(
                        row=row_number,
                        column=self._seller_link_column,
                    ).value
                    or ""
            )

            try:
                card = CardToPars.model_validate(data)
            except Exception as error:
                raise ValueError(
                    f"Не удалось прочитать строку {row_number}: {error}"
                ) from error

            original_link = card.seller_link
            self._rows.append((row_number, card, original_link))
            cards.append(card)
        return cards

    @property
    def output_path(self) -> Path:
        return self.path.with_name(f"{self.path.stem}_with_seller_links.xlsx")

    def save(
            self,
            path: str | Path | None = None,
            *,
            replace_seller_links: bool = False,
    ) -> Path:
        """Сохранить отчёт, при необходимости заменив все ссылки продавцов."""
        target = Path(path).expanduser().resolve() if path else self.output_path
        target.parent.mkdir(parents=True, exist_ok=True)

        for row_number, card, original_link in self._rows:
            if not replace_seller_links and (original_link or not card.seller_link):
                continue
            self.sheet.cell(
                row=row_number,
                column=self._seller_link_column,
                value=card.seller_link or None,
            )

        self.workbook.save(target)
        print(f"Отчёт со ссылками сохранён: {target} (строк: {len(self.cards)})")
        return target

    def close(self) -> None:
        self.workbook.close()
