from pydantic import BaseModel, Field


class FrontendBundleInfo(BaseModel):
    """Версия собранного интерфейса и размер архива с ним.

    Версия — это sha256 от содержимого каталога сборки. Локальное приложение
    подставляет её в имя каталога кэша, поэтому набор символов ограничен
    схемой: с сервера приходят данные, а не готовый путь.
    """

    version: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
