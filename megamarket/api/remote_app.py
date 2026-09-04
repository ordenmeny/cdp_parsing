from contextlib import asynccontextmanager

from fastapi import FastAPI

from megamarket.api.remote_sellers import router as sellers_router
from megamarket.db.helper import async_session_manager, sync_session_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await async_session_manager.dispose()
    sync_session_manager.dispose()


app = FastAPI(title="Megamarket Remote API", lifespan=lifespan)
app.include_router(sellers_router)
