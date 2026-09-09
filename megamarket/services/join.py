import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from megamarket.storage.report import (
    joined_report_filename,
    merge_excel_reports,
)


# Объединять один файл нечего, а полсотни отчётов за раз уже перекрывают любой
# разумный запуск. Ограничение на размер — как у проверки продавцов.
MIN_FILES = 2
MAX_FILES = 50
MAX_FILE_SIZE = 50 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class JoinResult:
    """Готовое объединение и папка, которую нужно убрать после отдачи."""

    directory: Path
    output_path: Path
    filename: str
    files_count: int
    rows_count: int


async def join_reports(uploads: Sequence[UploadFile]) -> JoinResult:
    """Сложить загруженные отчёты в один файл."""
    if len(uploads) < MIN_FILES:
        await _close(uploads)
        raise ValueError("Выберите хотя бы два файла .xlsx для объединения")
    if len(uploads) > MAX_FILES:
        await _close(uploads)
        raise ValueError(f"За один раз объединяется не больше {MAX_FILES} файлов")

    directory = Path(tempfile.mkdtemp(prefix="join-reports-"))
    try:
        sources = [
            # Своя подпапка на файл: имена загруженных отчётов совпадают чаще,
            # чем кажется, а различать их по ним ещё придётся в ошибках.
            await _save(upload, directory / "sources" / str(number))
            for number, upload in enumerate(uploads, start=1)
        ]
        filename = joined_report_filename()
        output_path = directory / "output" / filename
        # openpyxl работает синхронно, а объединение — это всё, чем занят
        # запрос: держать на нём цикл событий незачем.
        rows = await run_in_threadpool(merge_excel_reports, sources, output_path)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise

    return JoinResult(
        directory=directory,
        output_path=output_path,
        filename=filename,
        files_count=len(sources),
        rows_count=rows,
    )


async def _save(upload: UploadFile, directory: Path) -> Path:
    filename = Path(upload.filename or "").name
    if not filename or Path(filename).suffix.casefold() != ".xlsx":
        raise ValueError(
            f"Ожидаются файлы с расширением .xlsx, получен «{filename or '—'}»"
        )

    directory.mkdir(parents=True)
    target = directory / filename
    size = 0
    try:
        with target.open("wb") as stream:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise ValueError(
                        f"Размер файла «{filename}» превышает "
                        f"{MAX_FILE_SIZE // (1024 * 1024)} МБ"
                    )
                stream.write(chunk)
    finally:
        await upload.close()
    return target


async def _close(uploads: Sequence[UploadFile]) -> None:
    for upload in uploads:
        await upload.close()
