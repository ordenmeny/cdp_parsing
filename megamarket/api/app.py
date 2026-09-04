from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from megamarket.api.parser import router as parser_router
from megamarket.api.sellers import router as sellers_router
from megamarket.config import BASE_DIR


app = FastAPI(title="Megamarket Local API")
app.include_router(sellers_router)
app.include_router(parser_router)

frontend_dist = BASE_DIR / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=frontend_dist, html=True),
        name="frontend",
    )
