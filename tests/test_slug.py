import unittest

from megamarket.slug import SlugifyCard


class SlugifyCardTests(unittest.TestCase):
    def test_removes_dot_without_splitting_domain_like_name(self):
        self.assertEqual(SlugifyCard._slugify("embeq.store"), "embeqstore")
        self.assertEqual(SlugifyCard._slugify("Кувалда.ру"), "kuvaldaru")

    def test_preserves_word_separators(self):
        self.assertEqual(
            SlugifyCard._slugify("Юникс-Фитнес DBS"),
            "yuniks-fitnes-dbs",
        )

    def test_apostrophe_splits_words_instead_of_gluing_them(self):
        self.assertEqual(SlugifyCard._slugify("О'КЕЙ - Купер"), "o-key-kuper")
        self.assertEqual(SlugifyCard._slugify("О'КЕЙ"), "o-key")

    def test_apostrophe_is_recognised_in_any_shape(self):
        # В данных встречаются и типографский апостроф, и гравис вместо него.
        for name in ("О’КЕЙ - Купер", "О‘КЕЙ - Купер", "О`КЕЙ - Купер"):
            self.assertEqual(SlugifyCard._slugify(name), "o-key-kuper", name)

    def test_uses_megamarket_cyrillic_transliteration(self):
        self.assertEqual(SlugifyCard._slugify("Перекрёсток"), "perekrestok")
        self.assertEqual(SlugifyCard._slugify("ХОБОТ"), "hobot")


if __name__ == "__main__":
    unittest.main()
