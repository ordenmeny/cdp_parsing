from collections.abc import Sequence

from pydantic import BaseModel


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def read_query() -> str:
    return input("Поисковый запрос: ").strip()


def print_cards(cards: Sequence[BaseModel]) -> None:
    """Печатает поля модели в порядке объявления, первое — в строке с номером."""
    print(f"Собрано карточек: {len(cards)}")
    for number, card in enumerate(cards, start=1):
        (first, _), *rest = type(card).model_fields.items()
        print(f"{number}. {getattr(card, first)}")
        for name, field in rest:
            print(f"   {field.title or name}: {getattr(card, name) or '—'}")
