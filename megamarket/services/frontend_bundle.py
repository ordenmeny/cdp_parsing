import gzip
import hashlib
import io
import tarfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from megamarket.config import FRONTEND_DIST_DIR


class FrontendBundleMissing(RuntimeError):
    """В образе нет собранного интерфейса."""


@dataclass(frozen=True, slots=True)
class FrontendBundle:
    version: str
    archive: bytes


def bundle_files(directory: Path) -> list[Path]:
    """Файлы сборки в устойчивом порядке.

    Порядок задаёт и версию, и содержимое архива, поэтому он не может зависеть
    от того, как файловая система перечисляет каталог.
    """
    return sorted(path for path in directory.rglob("*") if path.is_file())


def bundle_version(directory: Path, files: list[Path]) -> str:
    """Отпечаток сборки: имена файлов плюс их содержимое.

    Время изменения не участвует — пересборка того же кода не должна заставлять
    пользователей заново скачивать тот же интерфейс.
    """
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def build_archive(directory: Path, files: list[Path]) -> bytes:
    """Собрать tar.gz без изменяющихся от прогона к прогону полей."""
    buffer = io.BytesIO()
    # mtime=0 в gzip и обнулённые владельцы в tar: одинаковая сборка даёт
    # одинаковый архив, и кэши по пути к пользователю не промахиваются.
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w|") as archive:
            for path in files:
                arcname = path.relative_to(directory).as_posix()
                info = archive.gettarinfo(str(path), arcname=arcname)
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
    return buffer.getvalue()


@lru_cache(maxsize=4)
def get_frontend_bundle(directory: Path = FRONTEND_DIST_DIR) -> FrontendBundle:
    """Архив интерфейса для раздачи локальным приложениям.

    Каталог сборки внутри контейнера не меняется, поэтому архив собирается один
    раз на процесс.
    """
    if not (directory / "index.html").is_file():
        raise FrontendBundleMissing(
            f"Собранный интерфейс не найден: {directory}"
        )
    files = bundle_files(directory)
    return FrontendBundle(
        version=bundle_version(directory, files),
        archive=build_archive(directory, files),
    )
