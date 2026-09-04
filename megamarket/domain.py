from enum import StrEnum

from pydantic import BaseModel, Field


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


class CardToPars(BaseModel):
    title: str = Field(title="Название")
    price: str = Field(title="Цена")
    seller: str = Field(title="Продавец")
    card_link: str = Field(title="Ссылка на карточку")
    image_link: str = Field(default="", title="Ссылка на изображение")
    stock: Stock = Field(default=Stock.OUT_OF_STOCK, title="Наличие")
    seller_link: str = Field(default="", title="Ссылка на продавца")


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
