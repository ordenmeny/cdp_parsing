from dataclasses import dataclass


@dataclass
class CardToPars:
    title: str
    price: str
    seller: str
    card_link: str
    seller_link: str = ""
