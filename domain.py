from dataclasses import dataclass


@dataclass
class CardToPars:
    title: str
    price: str
    seller: str
    card_link: str
    in_stock: bool = False
    seller_link: str = ""
