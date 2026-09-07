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

    def test_uses_megamarket_cyrillic_transliteration(self):
        self.assertEqual(SlugifyCard._slugify("Перекрёсток"), "perekrestok")
        self.assertEqual(SlugifyCard._slugify("ХОБОТ"), "hobot")


if __name__ == "__main__":
    unittest.main()
