import hashlib
import re
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from megamarket.utils import normalize_link


class Stock(StrEnum):
    IN_STOCK = "InStock"
    OUT_OF_STOCK = "OutOfStock"


class SellerStatus(StrEnum):
    CORRECT = "correct"
    UNCONFIRMED = "unconfirmed"
    INCORRECT = "incorrect"


class SellerObservationState(StrEnum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


# Идентификатор считаем от ссылки на карточку — она однозначно определяет
# товар у продавца, по ней же карточки и различаются при сборе. Шесть байт
# отпечатка дают число до 2^48: столько Excel держит без потери точности
# (у него ровно 2^53), а совпадение двух разных ссылок при таком размере —
# событие, которого на любых мыслимых объёмах выдачи не случится.
PRODUCT_ID_BYTES = 6


def product_id_from_link(link: str) -> int:
    """Числовой идентификатор карточки, устойчивый от запуска к запуску."""
    if not link:
        return 0
    digest = hashlib.sha256(link.strip().encode("utf-8")).digest()
    return int.from_bytes(digest[:PRODUCT_ID_BYTES], "big")


# Значок валюты сайт рисует прямо в цене. Убираем только его, не трогая
# остальной текст: у части карточек рядом стоит «/шт» или «за 2 шт», и терять
# это вместе с рублём нельзя.
CURRENCY_MARK = re.compile(r"₽|(?<![^\W\d_])руб\.?(?![^\W\d_])", re.IGNORECASE)


def clean_price(value: str) -> str:
    """Цена без значка рубля: в файле он мешает считать."""
    return " ".join(CURRENCY_MARK.sub(" ", value).split())


def seller_id_from_link(link: str) -> str:
    """Идентификатор продавца на маркетплейсе, зашитый в ссылку на карточку."""
    if not link:
        return ""
    try:
        return normalize_link(link)
    except ValueError:
        return ""


class CardToPars(BaseModel):
    """Строка отчёта. Порядок полей задаёт порядок колонок в файле."""

    card_link: str = Field(title="Ссылка")
    title: str = Field(title="Название товара")
    # Бренд в выдаче не размечен: колонка есть, значения в ней нет.
    brand: str = Field(default="", title="Бренд")
    product_id: int = Field(default=0, title="ID карточки")
    # Описание живёт только внутри карточки товара, а заходить в неё нельзя.
    description: str = Field(default="", title="Описание товара")
    price: str = Field(title="Цены")
    rating: str = Field(default="", title="Рейтинг")
    seller: str = Field(title="Продавец")
    seller_link: str = Field(default="", title="Ссылка на продавца")
    seller_id: str = Field(default="", title="ID продавца на маркетплейсе")
    # Реквизиты продавца берутся из базы: в выдаче их нет, они появляются
    # после проверки продавца. У непроверенных остаются пустыми.
    official_name: str = Field(default="", title="Юр. Лицо")
    legal_address: str = Field(default="", title="Юр. Адрес")
    inn: str = Field(default="", title="ИНН продавца")
    ogrn: str = Field(default="", title="ОГРН")
    seller_phone: str = Field(default="", title="seller_phone")
    seller_email: str = Field(default="", title="seller_email")
    image_link: str = Field(default="", title="link")
    # Служебные колонки идут после заданных: наличие и запрос, по которому
    # строка попала в отчёт.
    stock: Stock = Field(default=Stock.OUT_OF_STOCK, title="Наличие")
    query: str = Field(default="", title="Запрос")

    @model_validator(mode="after")
    def _normalize(self):
        """Досчитать то, что выводится из уже собранного.

        Карточка создаётся в нескольких местах — при разборе выдачи и при
        чтении готового отчёта, — поэтому считаем здесь, чтобы значения не
        зависели от того, каким путём карточка появилась.
        """
        if not self.product_id:
            self.product_id = product_id_from_link(self.card_link)
        if not self.seller_id:
            self.seller_id = seller_id_from_link(self.card_link)
        self.price = clean_price(self.price)
        return self


class SellerInfo(BaseModel):
    """Данные продавца, прочитанные с его страницы."""

    seller_id: str = Field(title="Идентификатор продавца")
    name: str = Field(title="Название")
    slug: str = Field(default="", title="Слаг магазина")
    official_name: str = Field(default="", title="Официальное название")
    ogrn: str = Field(default="", title="ОГРН")
    inn: str = Field(default="", title="ИНН")
    email: str = Field(default="", title="E-mail")
    phone: str = Field(default="", title="Телефон")
    legal_form: str = Field(default="", title="Форма")
    address: str = Field(default="", title="Адрес")
    rating: float | None = Field(default=None, title="Рейтинг")
