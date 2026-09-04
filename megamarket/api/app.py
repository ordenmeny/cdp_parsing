import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from megamarket.api.parser import router as parser_router
from megamarket.api.sellers import router as sellers_router
from megamarket.clients.remote_api import RemoteApiClient
from megamarket.config import (
    FRONTEND_DIST_DIR,
    get_remote_api_settings,
    settings,
)
from megamarket.services.frontend_sync import cached_bundle, sync_frontend


logger = logging.getLogger(__name__)


async def prepare_frontend() -> Path | None:
    """Найти интерфейс, который приложение будет раздавать в этом запуске.

    Порядок такой: свежая версия с сервера, иначе скачанная раньше, иначе
    собранная вручную рядом с исходниками. Ни одна неудача здесь не должна
    мешать запуску — API нужен пользователю и без интерфейса.
    """
    cache_dir = settings.frontend_cache_dir
    client: RemoteApiClient | None = None
    try:
        client = RemoteApiClient(get_remote_api_settings())
        directory = await sync_frontend(
            client,
            cache_dir=cache_dir,
            timeout=settings.frontend_sync_timeout,
        )
        logger.info("Интерфейс получен с сервера: %s", directory)
        return directory
    except Exception as error:  # noqa: BLE001 — причин много, реакция одна
        logger.warning("Не удалось обновить интерфейс с сервера: %s", error)
    finally:
        if client is not None:
            await client.close()

    cached = cached_bundle(cache_dir)
    if cached is not None:
        logger.warning(
            "Открыт интерфейс, скачанный ранее: %s",
            cached.directory,
        )
        return cached.directory
    if (FRONTEND_DIST_DIR / "index.html").is_file():
        logger.warning(
            "Открыт интерфейс из локальной сборки: %s",
            FRONTEND_DIST_DIR,
        )
        return FRONTEND_DIST_DIR
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    directory = await prepare_frontend()
    if directory is None:
        logger.error(
            "Интерфейс недоступен: сервер не отвечает, скачанной копии нет. "
            "Проверьте PARSER_REMOTE_API_URL и доступность сервера."
        )
    else:
        # Монтируем после маршрутов API: «/» перехватывает всё остальное.
        app.mount(
            "/",
            StaticFiles(directory=directory, html=True),
            name="frontend",
        )
    yield


app = FastAPI(title="Megamarket Local API", lifespan=lifespan)
app.include_router(sellers_router)
app.include_router(parser_router)
