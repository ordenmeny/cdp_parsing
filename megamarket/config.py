from pathlib import Path

from pydantic import (
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_CONFIG = SettingsConfigDict(
    env_prefix="PARSER_",
    env_file=BASE_DIR / ".env",
    env_file_encoding="utf-8",
    extra="ignore",
)


class ParserSettings(BaseSettings):
    model_config = ENV_CONFIG

    # Сколько собирать. None — пока сайт отдаёт результаты.
    number_pages: int | None = None  # страниц выдачи
    number_items: int | None = None  # карточек с одной страницы
    number_visits: int | None = None  # заходов в карточки за продавцами
    number_clicks: int | None = None  # нажатий «Показать ещё» при scrolling

    # После последней страницы сайт может начать выдачу заново (после 64-й —
    # снова вторая). Страница без единой новой карточки — повтор всегда; кроме
    # того, повтором считается страница, где новых меньше repeat_new_share от
    # обычного прироста за страницу в этом прогоне. Ноль в этой настройке
    # оставляет только строгое правило «ни одной новой».
    repeat_new_share: float = 0.25
    repeat_pages_limit: PositiveInt = 2

    captcha_timeout: int = 300
    # Обычный элемент фильтра должен появиться и переключиться быстро.
    filter_timeout: int = 15
    # Окно продавца на карточке: раскрывается сразу или не раскроется вовсе.
    popover_timeout: int = 10
    # Сколько ждать состояния страницы магазина после её загрузки.
    seller_page_timeout: int = 30
    # Сколько ждать прироста карточек после нажатия «Показать ещё».
    more_button_timeout: int = 30

    # Паузы между переходами.
    page_delay_min: NonNegativeInt = 5
    page_delay_max: NonNegativeInt = 10
    long_pause_every_pages: PositiveInt = 4
    long_pause_min: NonNegativeInt = 10
    long_pause_max: NonNegativeInt = 11
    card_delay: NonNegativeFloat = 7
    card_close_delay: NonNegativeFloat = 8

    @model_validator(mode="after")
    def _validate_delay_ranges(self):
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


class DatabaseSettings(BaseSettings):
    """Параметры подключения приложения к PostgreSQL."""

    model_config = ENV_CONFIG

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_echo: bool

    def _url(self, drivername: str) -> str:
        return URL.create(
            drivername=drivername,
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        ).render_as_string(hide_password=False)

    @property
    def sync_db_url(self) -> str:
        return self._url("postgresql+psycopg")

    @property
    def async_db_url(self) -> str:
        return self._url("postgresql+asyncpg")


class Settings(BaseSettings):
    """Окружение: куда складывать результат, какой сайт, какой браузер."""

    model_config = ENV_CONFIG

    report_dir: Path = BASE_DIR / "output"

    base_url: str = "https://megamarket.ru"

    browser_host: str = "127.0.0.1"
    browser_port: int = 51112
    cdp_metrics: bool = False

    # Своя модель настроек, а не вложенное поле: имена переменных окружения
    # остаются прежними (PARSER_NUMBER_PAGES, а не PARSER_PARSER__...).
    parser: ParserSettings = Field(default_factory=ParserSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)

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
parser_settings = settings.parser
