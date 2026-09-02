from pathlib import Path

from pydantic import (
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
)
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
    browser_port: int = 52222

    # Сколько собирать. None — пока сайт отдаёт результаты.
    number_pages: int | None = None  # страниц выдачи
    number_items: int | None = None # карточек с одной страницы
    number_visits: int | None = None  # заходов в карточки за продавцами

    captcha_timeout: int = 300
    # Обычный элемент фильтра должен появиться и переключиться быстро.
    filter_timeout: int = 15
    # Окно продавца на карточке: раскрывается сразу или не раскроется вовсе.
    popover_timeout: int = 10

    # Паузы между переходами.
    page_delay_min: NonNegativeInt = 15
    page_delay_max: NonNegativeInt = 25
    long_pause_every_pages: PositiveInt = 4
    long_pause_min: NonNegativeInt = 2 * 60
    long_pause_max: NonNegativeInt = 160
    card_delay: NonNegativeFloat = 7
    card_close_delay: NonNegativeFloat = 8

    @field_validator("base_url")
    @classmethod
    def _drop_trailing_slash(cls, value: str) -> str:
        """Адреса склеиваем строками, поэтому хвостовой слеш только помешает."""
        return value.rstrip("/")

    @model_validator(mode="after")
    def _validate_page_delay_range(self):
        if self.page_delay_min > self.page_delay_max:
            raise ValueError(
                "PARSER_PAGE_DELAY_MIN не может быть больше "
                "PARSER_PAGE_DELAY_MAX."
            )
        if self.long_pause_min > self.long_pause_max:
            raise ValueError(
                "PARSER_LONG_PAUSE_MIN не может быть больше "
                "PARSER_LONG_PAUSE_MAX."
            )
        return self

    @property
    def browser_endpoint(self) -> str:
        """Адрес CDP уже запущенного браузера."""
        return f"http://{self.browser_host}:{self.browser_port}"


settings = Settings()
