import io
import json
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from megamarket.schemas.frontend import FrontendBundleInfo

# Собранный интерфейс весит сотни килобайт. Запас на порядки закрывает рост
# приложения и всё равно не даёт залить пользователю случайный гигабайт.
MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
MAX_UNPACKED_SIZE = 256 * 1024 * 1024

BUNDLES_DIR = "bundles"
POINTER_NAME = "current.json"
STAGING_SUFFIX = ".part"


class FrontendSource(Protocol):
    """Часть удалённого API, от которой зависит синхронизация интерфейса."""

    async def get_frontend_info(self, *, timeout: float) -> FrontendBundleInfo:
        ...

    async def download_frontend_bundle(
            self,
            *,
            timeout: float,
            max_size: int,
    ) -> bytes:
        ...


@dataclass(frozen=True, slots=True)
class CachedBundle:
    version: str
    directory: Path


def cached_bundle(cache_dir: Path) -> CachedBundle | None:
    """Интерфейс, скачанный в прошлые запуски, если он на месте и целый."""
    try:
        payload = json.loads(
            (cache_dir / POINTER_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    version = payload.get("version")
    # Версия попадает в путь, поэтому проверяем её так же строго, как схема.
    if not isinstance(version, str) or not _is_version(version):
        return None
    directory = cache_dir / BUNDLES_DIR / version
    if not (directory / "index.html").is_file():
        return None
    return CachedBundle(version=version, directory=directory)


async def sync_frontend(
        source: FrontendSource,
        *,
        cache_dir: Path,
        timeout: float,
) -> Path:
    """Привести локальный кэш интерфейса к версии, которую отдаёт сервер."""
    info = await source.get_frontend_info(timeout=timeout)
    cached = cached_bundle(cache_dir)
    if cached is not None and cached.version == info.version:
        return cached.directory

    archive = await source.download_frontend_bundle(
        timeout=timeout,
        max_size=MAX_ARCHIVE_SIZE,
    )
    directory = _unpack(archive, cache_dir=cache_dir, version=info.version)
    _write_pointer(cache_dir, info.version)
    _prune(cache_dir, keep=info.version)
    return directory


def _is_version(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _unpack(archive: bytes, *, cache_dir: Path, version: str) -> Path:
    """Распаковать архив так, чтобы полураспакованный каталог не смонтировался.

    Распаковка идёт в отдельный каталог и переезжает на своё место одним
    переименованием: обрыв связи или падение процесса оставляют прошлую версию
    рабочей.
    """
    bundles = cache_dir / BUNDLES_DIR
    bundles.mkdir(parents=True, exist_ok=True)
    target = bundles / version
    staging = bundles / f"{version}{STAGING_SUFFIX}"

    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            members = tar.getmembers()
            unpacked = sum(member.size for member in members)
            if unpacked > MAX_UNPACKED_SIZE:
                raise ValueError(
                    "Распакованный интерфейс больше допустимых "
                    f"{MAX_UNPACKED_SIZE} байт"
                )
            # filter="data" отсекает выход за пределы каталога, ссылки и
            # спецфайлы: архив приходит по сети, разбирать его на доверии нельзя.
            tar.extractall(path=staging, filter="data")
        if not (staging / "index.html").is_file():
            raise ValueError("В архиве интерфейса нет index.html")
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def _write_pointer(cache_dir: Path, version: str) -> None:
    pointer = cache_dir / POINTER_NAME
    staging = cache_dir / f"{POINTER_NAME}{STAGING_SUFFIX}"
    staging.write_text(
        json.dumps({"version": version}),
        encoding="utf-8",
    )
    staging.replace(pointer)


def _prune(cache_dir: Path, *, keep: str) -> None:
    """Убрать версии, на которые больше никто не смотрит."""
    bundles = cache_dir / BUNDLES_DIR
    try:
        entries = list(bundles.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name == keep or not entry.is_dir():
            continue
        shutil.rmtree(entry, ignore_errors=True)
