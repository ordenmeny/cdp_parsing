import unittest

from megamarket.cdp.extractors import (
    CardsExtraction,
    InStockControlProbe,
    PageProbe,
    build_cards_extractor_script,
    build_in_stock_control_probe_script,
    build_page_probe_script,
)


class ExtractorTests(unittest.TestCase):
    def test_page_probe_parses_expected_fields(self):
        probe = PageProbe.from_raw({
            "cards": 44,
            "notFound": False,
            "blockMarker": True,
            "heading": " Заголовок ",
            "readyState": "complete",
            "href": "https://example.test/catalog/",
        })

        self.assertEqual(probe.cards, 44)
        self.assertTrue(probe.block_marker)
        self.assertEqual(probe.ready_state, "complete")

    def test_cards_extraction_ignores_malformed_items(self):
        extraction = CardsExtraction.from_raw({
            "total": 2,
            "items": [
                {
                    "index": 0,
                    "title": "Товар",
                    "price": "100 ₽",
                    "seller": "Продавец",
                    "href": "/product/",
                    "image": "image.jpg",
                },
                None,
            ],
        })

        self.assertEqual(extraction.total, 2)
        self.assertEqual(len(extraction.items), 1)

    def test_scripts_are_iife_and_quote_selectors(self):
        probe = build_page_probe_script(
            card_selector='[data-value="quoted"]',
            not_found_selector=".empty",
            block_marker_selector="#blocked",
        )
        cards = build_cards_extractor_script(
            card_selector=".card",
            title_selector=".title",
            price_selector=".price",
            seller_selector=".seller",
            image_selector=".image",
        )

        self.assertTrue(probe.lstrip().startswith("(() =>"))
        self.assertTrue(cards.lstrip().startswith("(() =>"))
        self.assertIn(r'[data-value=\"quoted\"]', probe)

    def test_in_stock_probe_and_script(self):
        probe = InStockControlProbe.from_raw({
            "found": True,
            "selected": False,
        })
        script = build_in_stock_control_probe_script(
            toggle_selector=".toggle",
            label_selector=".label",
            control_selector=".control",
            selected_class="selected",
            expected_label="В наличии",
        )

        self.assertTrue(probe.found)
        self.assertFalse(probe.selected)
        self.assertTrue(script.lstrip().startswith("(() =>"))
        self.assertNotIn("console.", script)
        self.assertNotIn("setAttribute", script)

    def test_extractor_reads_whole_dom_and_leaves_no_traces(self):
        script = build_cards_extractor_script(
            card_selector=".card",
            title_selector=".title",
            price_selector=".price",
            seller_selector=".seller",
            image_selector=".image",
        )

        self.assertTrue(script.lstrip().startswith("(() =>"))
        self.assertIn("cards.map(", script)
        # Смещения быть не должно: страница читается целиком.
        self.assertNotIn("Offset", script)
        self.assertNotIn("slice(", script)
        # Скрипт не должен оставлять следов в странице.
        self.assertNotIn("console.", script)
        self.assertNotIn("setAttribute", script)
        self.assertNotIn("window.", script)


if __name__ == "__main__":
    unittest.main()
