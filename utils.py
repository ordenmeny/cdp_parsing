from collections.abc import Sequence
from urllib.parse import parse_qs, unquote, urlsplit

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


def normalize_link(link: str) -> str:
    """Возвращает уникальный slug карточки товара из ссылки Megamarket."""
    parts = urlsplit(link.strip())
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError("Ожидалась абсолютная ссылка, начинающаяся с https://")

    path_parts = [unquote(part) for part in parts.path.split("/") if part]
    if path_parts[:2] == ["catalog", "details"] and len(path_parts) == 3:
        return path_parts[-1]

    params = parse_qs(parts.query) | parse_qs(parts.fragment.lstrip("?"))
    if path_parts[:2] == ["promo-page", "details"] and params.get("slug"):
        return params["slug"][0]

    raise ValueError("Не удалось определить идентификатор карточки товара")
