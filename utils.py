import sys
from collections.abc import Sequence
from typing import Protocol


class _Card(Protocol):
    title: str
    price: str
    seller: str
    card_link: str
    seller_link: str


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def read_query() -> str:
    print("Поисковый запрос: ", end="", flush=True)
    raw_query = sys.stdin.buffer.readline().rstrip(b"\r\n")

    try:
        return raw_query.decode("utf-8")
    except UnicodeDecodeError:
        return raw_query.decode("cp1251")


def print_cards(cards: Sequence[_Card]) -> None:
    print(f"Собрано карточек: {len(cards)}")
    for number, card in enumerate(cards, start=1):
        print(
            f"{number}. {card.title}\n"
            f"   Цена: {card.price}\n"
            f"   Продавец: {card.seller}\n"
            f"   Ссылка на карточку: {card.card_link}\n"
            f"   Ссылка на продавца: {card.seller_link or '—'}"
        )
