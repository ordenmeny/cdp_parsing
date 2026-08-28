from pathlib import Path

from pydantic import NonNegativeFloat, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PARSER_",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    report_dir: Path = BASE_DIR / "output"

    base_url: str = "https://megamarket.ru"

    browser_host: str = "127.0.0.1"
    browser_port: int = 51111

    # Сколько собирать. None — пока сайт отдаёт результаты.
    number_pages: int | None = 3  # страниц выдачи
    number_items: int | None = 4  # карточек с одной страницы
    number_visits: int | None = None  # заходов в карточки за продавцами

    captcha_timeout: int = 300
    # Окно продавца на карточке: раскрывается сразу или не раскроется вовсе.
    popover_timeout: int = 10

    # Паузы между переходами.
    page_delay: int = 2
    card_delay: int = 2

    @field_validator("base_url")
    @classmethod
    def _drop_trailing_slash(cls, value: str) -> str:
        """Адреса склеиваем строками, поэтому хвостовой слеш только помешает."""
        return value.rstrip("/")

    @property
    def browser_endpoint(self) -> str:
        """Адрес CDP уже запущенного браузера."""
        return f"http://{self.browser_host}:{self.browser_port}"


settings = Settings()
