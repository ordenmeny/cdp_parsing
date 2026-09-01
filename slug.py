# Юникс-Фитнес DBS https://megamarket.ru/shop/yuniks-fitnes-dbs/
# Button Shop https://megamarket.ru/shop/button-shop/

import re
import unicodedata

from domain import CardToPars

from config import settings

_CYRILLIC_TO_LATIN = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "yo",
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
        "х": "kh",
        "ц": "ts",
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


class SlugifyCard:
    def __init__(self, cards: list[CardToPars]):
        self.cards = cards

    def get_link(self, slug: str):
        return f'{settings.base_url}/shop/{slug}/'

    def set_sellers_slugs(self):
        for i in self.cards:
            slug = self._slugify(i.seller)
            i.seller_link = self.get_link(slug)

    @staticmethod
    def _slugify(value: str) -> str:
        """Convert a string to a lowercase ASCII slug."""
        if not isinstance(value, str):
            raise TypeError("value must be a string")

        transliterated = value.lower().translate(_CYRILLIC_TO_LATIN)
        normalized = unicodedata.normalize("NFKD", transliterated)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
