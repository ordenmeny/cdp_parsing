# Юникс-Фитнес DBS https://megamarket.ru/shop/yuniks-fitnes-dbs/
# Button Shop https://megamarket.ru/shop/button-shop/

import re
import unicodedata

from megamarket.domain import CardToPars

from megamarket.config import settings

_CYRILLIC_TO_LATIN = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "c",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


# В названиях магазинов апостроф приходит в любом начертании: прямой,
# типографский, модификатор и даже гравис вместо него.
_APOSTROPHES = re.compile(r"['’‘`´ʼʹ′]+")


class SlugifyCard:
    def __init__(self, cards: list[CardToPars]):
        self.cards = cards

    def get_link(self, slug: str):
        return f'{settings.base_url}/shop/{slug}/'

    @classmethod
    def link_for_seller(cls, name: str) -> str:
        """Сформировать предполагаемую ссылку магазина по имени продавца."""
        return f"{settings.base_url}/shop/{cls._slugify(name)}/"

    def set_sellers_slugs(self):
        for i in self.cards:
            i.seller_link = self.link_for_seller(i.seller)

    @staticmethod
    def _slugify(value: str) -> str:
        """Convert a string to a lowercase ASCII slug."""
        if not isinstance(value, str):
            raise TypeError("value must be a string")

        transliterated = value.lower().translate(_CYRILLIC_TO_LATIN)
        # Апостроф — исключение из правила ниже: Megamarket считает его
        # разделителем, а не украшением. ``О'КЕЙ - Купер`` открывается как
        # ``/shop/o-key-kuper/``. Замену делаем до перевода в ASCII: типографский
        # апостроф там просто выпал бы, и слова склеились.
        separated = _APOSTROPHES.sub(" ", transliterated)
        normalized = unicodedata.normalize("NFKD", separated)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        # Пунктуация внутри названия магазина не является разделителем в
        # слагах Megamarket: ``Кувалда.ру`` превращается в ``kuvaldaru``.
        # Пробелы и дефисы при этом по-прежнему разделяют слова.
        without_punctuation = re.sub(r"[^a-z0-9\s_-]+", "", ascii_value)
        return re.sub(r"[\s_-]+", "-", without_punctuation).strip("-")
