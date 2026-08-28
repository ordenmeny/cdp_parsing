from enum import StrEnum

from pydantic import BaseModel, Field


class Stock(StrEnum):
    IN_STOCK = "InStock"
    OUT_OF_STOCK = "OutOfStock"


class CardToPars(BaseModel):
    title: str = Field(title="Название")
    price: str = Field(title="Цена")
    seller: str = Field(title="Продавец")
    card_link: str = Field(title="Ссылка на карточку")
    stock: Stock = Field(default=Stock.OUT_OF_STOCK, title="Наличие")
    seller_link: str = Field(default="", title="Ссылка на продавца")
