from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from megamarket.api.parser import router as parser_router
from megamarket.api.sellers import router as sellers_router
from megamarket.config import BASE_DIR
from megamarket.db.helper import async_session_manager, sync_session_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await async_session_manager.dispose()
    sync_session_manager.dispose()


app = FastAPI(title="Megamarket API", lifespan=lifespan)
app.include_router(sellers_router)
app.include_router(parser_router)

frontend_dist = BASE_DIR / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=frontend_dist, html=True),
        name="frontend",
    )
