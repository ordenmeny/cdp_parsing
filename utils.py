from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
import random
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import BaseModel

from config import settings


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def get_random_delay(
        min_seconds: int | None = None,
        max_seconds: int | None = None,
) -> int:
    """Вернуть случайную задержку из настроенного диапазона."""
    if min_seconds is None:
        min_seconds = settings.page_delay_min
    if max_seconds is None:
        max_seconds = settings.page_delay_max
    if min_seconds < 0 or max_seconds < 0:
        raise ValueError("Время ожидания не может быть отрицательным.")
    if min_seconds > max_seconds:
        raise ValueError("Минимальное время ожидания больше максимального.")
    return random.randint(min_seconds, max_seconds)


def read_query() -> str:
    return input("Поисковый запрос: ").strip()


@dataclass(frozen=True, slots=True)
class ParseCommand:
    query: str
    start_page: int = 1


@dataclass(frozen=True, slots=True)
class ScrollCommand:
    """Сбор без перехода по страницам: догрузка «Показать ещё» на месте."""

    query: str


@dataclass(frozen=True, slots=True)
class JoinCommand:
    directory: Path


type InputCommand = ParseCommand | ScrollCommand | JoinCommand


def parse_input_command(value: str) -> InputCommand:
    """Разобрать поисковый запрос, продолжение или команду объединения."""
    value = value.strip()
    if not value:
        raise ValueError(
            "Введите поисковый запрос, scrolling||<запрос> или join||<папка>."
        )

    head, separator, tail = value.partition("||")
    if not separator:
        return ParseCommand(query=value)

    head = head.strip()
    tail = tail.strip()
    if head.casefold() == "join":
        path = tail.strip('"')
        if not path:
            raise ValueError("После join|| укажите путь до папки с отчётами.")
        return JoinCommand(directory=Path(path).expanduser())

    if head.casefold() == "scrolling":
        # Всё после разделителя — сам запрос: номер страницы этому потоку
        # не нужен, а «||» внутри запроса встречаться не должен.
        query = tail.strip('"')
        if not query:
            raise ValueError("После scrolling|| укажите поисковый запрос.")
        return ScrollCommand(query=query)

    if not head:
        raise ValueError("Перед || должен быть поисковый запрос.")
    if not tail.isdecimal() or int(tail) < 1:
        raise ValueError("После || укажите номер начальной страницы от 1 и выше.")
    return ParseCommand(query=head, start_page=int(tail))


def read_command() -> InputCommand:
    """Запрашивать команду, пока пользователь не введёт корректное значение."""
    while True:
        entered = input(
            "Запрос[||страница], scrolling||<запрос> или join||<папка>: "
        )
        try:
            return parse_input_command(entered)
        except ValueError as error:
            print(f"Ошибка ввода: {error}")



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
