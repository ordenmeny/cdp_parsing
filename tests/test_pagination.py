import unittest
import re
from unittest.mock import AsyncMock

from megamarket.domain import Stock
from megamarket.exceptions import PageParseError
from megamarket.parsers.parsing import MegamarketParsePage


class _DomainContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _ChildElement:
    def __init__(self, *, text: str = "", href: str = "") -> None:
        self._text = text
        self.attributes = {"href": href} if href else {}

    async def apply(self, expression: str) -> str:
        return self._text

    @property
    def text(self) -> str:
        return self._text


class _CardElement:
    def __init__(self, number: int) -> None:
        self.number = number
        self._children = {
            MegamarketParsePage.TITLE_SELECTOR: _ChildElement(
                text=f"Товар {number}",
                href=f"/catalog/product-{number}/",
            ),
            MegamarketParsePage.PRICE_SELECTOR: _ChildElement(
                text=f"{number} 000 ₽"
            ),
            MegamarketParsePage.SELLER_SELECTOR: _ChildElement(
                text=f"Продавец {number}"
            ),
        }

    async def query_selector(self, selector: str):
        return self._children.get(selector)


class _CDP:
    class DOM:
        @staticmethod
        async def get_document(*, depth: int):
            return object()


class _FakePage:
    def __init__(self) -> None:
        self.cdp = _CDP()
        self.cards = []
        self.visible_count = 0
        self.pending_counts = []
        self.current_url = "about:blank"
        self.navigations = []
        self.evaluate_calls = []
        self.domain_calls = 0
        self._dom_generation = 0
        self.xpath_calls = []
        self.select_all_calls = 0
        self.not_found = False
        self.block_marker = False
        self.heading = ""
        self.navigation_error = ""
        self.navigation_timeout = False
        # Карточки в DOM есть, но нужных полей в них нет — так выглядит
        # смена разметки на сайте.
        self.broken_markup = False

    def domain_enabled(self, domain):
        self.domain_calls += 1
        return _DomainContext()

    async def navigate(self, url: str, **kwargs):
        self.current_url = url
        self.navigations.append((url, kwargs))
        if "/page-3/" in url:
            self.cards = []
            self.pending_counts = [0]
            self.not_found = True
        elif "/page-2/" in url:
            self.cards = [_CardElement(number) for number in range(4, 6)]
            # Вторая страница содержит только свои товары и отрисовывает их
            # постепенно, а не дополняет товарами DOM первой страницы.
            self.pending_counts = [1, 2]
            self.not_found = False
        else:
            self.cards = [_CardElement(number) for number in range(1, 4)]
            self.pending_counts = [3]
            self.not_found = False
        if self.navigation_timeout and "/page-" in url:
            raise TimeoutError
        return {"errorText": self.navigation_error}

    async def wait_for_selector(self, *args, **kwargs):
        return object()

    async def evaluate(self, expression: str):
        self.evaluate_calls.append(expression)
        if expression == "location.href":
            return self.current_url
        if "blockMarker:" in expression and "readyState:" in expression:
            if self.pending_counts:
                self.visible_count = self.pending_counts.pop(0)
            return {
                "cards": self.visible_count,
                "notFound": self.not_found,
                "blockMarker": self.block_marker,
                "heading": self.heading,
                "readyState": "complete",
                "href": self.current_url,
            }
        if "const cards = Array.from" in expression:
            return {
                "total": self.visible_count,
                "items": [
                    {
                        "index": index,
                        "title": "" if self.broken_markup else f"Товар {card.number}",
                        "price": f"{card.number} 000 ₽",
                        "seller": (
                            "" if self.broken_markup
                            else f"Продавец {card.number}"
                        ),
                        "href": (
                            "" if self.broken_markup
                            else f"/catalog/product-{card.number}/"
                        ),
                        "image": "",
                    }
                    for index, card in enumerate(
                        self.cards[:self.visible_count]
                    )
                ],
            }
        return ""

    async def select(self, *, selector: str | None = None, xpath: str | None = None):
        if xpath is not None:
            self.xpath_calls.append(xpath)
        return None

    async def select_all(self, selector: str):
        self.select_all_calls += 1
        if self.pending_counts:
            self.visible_count = self.pending_counts.pop(0)
        return list(self.cards[:self.visible_count])


class _ToggleElement:
    def __init__(self, page) -> None:
        self.page = page
        self.click_count = 0
        self._generation = -1

    async def mouse_click(self) -> None:
        self.click_count += 1
        self.page.in_stock_selected = True
        self.page.current_url += "#?filters=in-stock"

    @property
    def attributes(self) -> dict[str, str]:
        selected_class = (
            f" {MegamarketParsePage.IN_STOCK_SELECTED_CLASS}"
            if self.page.in_stock_selected
            else ""
        )
        return {
            "class": f"pui-toggle-control{selected_class}",
        }

    async def query_selector(self, selector: str):
        if selector == MegamarketParsePage.IN_STOCK_LABEL_SELECTOR:
            return _ChildElement(text="В наличии")
        if selector == MegamarketParsePage.IN_STOCK_CONTROL_SELECTOR:
            return self
        return None


class _FilterPage(_FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.in_stock_selected = False
        self.toggle = _ToggleElement(self)

    async def evaluate(self, expression: str):
        if "const toggles = Array.from" in expression:
            self.evaluate_calls.append(expression)
            return {
                "found": True,
                "selected": self.in_stock_selected,
            }
        return await super().evaluate(expression)

    async def select(self, *, selector: str | None = None, xpath: str | None = None):
        if xpath == MegamarketParsePage.IN_STOCK_CONTROL_XPATH:
            self.xpath_calls.append(xpath)
            return self.toggle
        return await super().select(selector=selector, xpath=xpath)


class PaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_state_priority_is_block_not_found_ready(self):
        page = _FakePage()
        page.visible_count = 3
        page.not_found = True
        page.block_marker = True
        page.heading = (
            "Запросы с вашего устройства похожи на автоматические"
        )
        parser = MegamarketParsePage(page, captcha_timeout=0)

        state = await parser.wait_page_state()

        self.assertEqual(state.value, "blocked")
        self.assertEqual(page.domain_calls, 0)

    async def test_page_complete_is_ready_even_before_cards_appear(self):
        page = _FakePage()
        page.visible_count = 0
        parser = MegamarketParsePage(page, captcha_timeout=0)

        state = await parser.wait_page_state()

        self.assertEqual(state.value, "ready")

    async def test_parse_current_page_uses_one_evaluate_without_dom(self):
        page = _FakePage()
        page.cards = [_CardElement(number) for number in range(1, 4)]
        page.visible_count = 3
        parser = MegamarketParsePage(page, number_items=2)

        cards = await parser.parse_current_page()

        self.assertEqual([card.title for card in cards], ["Товар 1", "Товар 2"])
        self.assertEqual(len(page.evaluate_calls), 1)
        self.assertIn("const cards = Array.from", page.evaluate_calls[0])
        self.assertEqual(page.domain_calls, 0)

    async def test_extractor_keeps_blank_price_and_discards_invalid_cards(self):
        page = _FakePage()
        page.evaluate = AsyncMock(return_value={
            "total": 4,
            "offset": 0,
            "items": [
                {
                    "index": 0,
                    "title": "Товар",
                    "price": "",
                    "seller": "Продавец",
                    "href": "/catalog/product/",
                    "image": "image.jpg",
                },
                {"index": 1, "title": "Без ссылки", "seller": "Продавец"},
                {"index": 2, "title": "", "seller": "Продавец", "href": "/2"},
                {"index": 3, "title": "Без продавца", "seller": "", "href": "/3"},
            ],
        })
        parser = MegamarketParsePage(page)

        cards = await parser.parse_current_page()

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].price, "")
        self.assertEqual(
            cards[0].card_link,
            "https://megamarket.ru/catalog/product/",
        )
        page.evaluate.assert_awaited_once_with(parser._cards_extractor_script)

    async def test_enables_in_stock_filter_with_element_click(self):
        page = _FilterPage()
        parser = MegamarketParsePage(
            page,
            in_stock_only=True,
            number_pages=1,
            page_delay=0,
            cards_load_timeout=0.1,
            cards_poll_interval=0,
            cards_stable_checks=1,
        )

        cards = await parser.parse("iphone")

        self.assertTrue(page.in_stock_selected)
        self.assertEqual(page.toggle.click_count, 1)
        self.assertEqual(page.domain_calls, 1)
        self.assertEqual(len(page.xpath_calls), 1)
        self.assertEqual(page.select_all_calls, 0)
        self.assertTrue(cards)
        self.assertTrue(all(card.stock is Stock.IN_STOCK for card in cards))

    def test_next_page_url_preserves_query_and_fragment(self):
        parser = MegamarketParsePage(_FakePage(), number_pages=2)
        regular = parser.build_page_url(
            "https://megamarket.ru/catalog/?q=iphone",
            2,
        )
        redirected = parser.build_page_url(
            "https://megamarket.ru/catalog/iphone-16/#?related_search=iphone",
            2,
        )

        self.assertEqual(
            regular,
            "https://megamarket.ru/catalog/page-2/?q=iphone",
        )
        self.assertEqual(
            redirected,
            "https://megamarket.ru/catalog/iphone-16/page-2/#?related_search=iphone",
        )

    async def test_parse_each_pagination_page_independently(self):
        page = _FakePage()
        parser = MegamarketParsePage(
            page,
            number_pages=2,
            page_delay=0,
            cards_load_timeout=0.1,
            cards_poll_interval=0,
            cards_stable_checks=1,
        )

        cards = await parser.parse("iphone")

        self.assertEqual([card.title for card in cards], [
            "Товар 1",
            "Товар 2",
            "Товар 3",
            "Товар 4",
            "Товар 5",
        ])
        self.assertEqual(len(page.navigations), 2)
        self.assertTrue(page.navigations[0][1]["wait_load"])
        self.assertTrue(page.navigations[1][1]["wait_load"])
        self.assertIn("/catalog/page-2/", page.navigations[1][0])

    async def test_parses_whole_dom_without_offset(self):
        """Разбор не опирается на смещение: страница читается целиком.

        Накопительная страница отдаёт карточки предыдущих страниц заново —
        отсекать их должна дедупликация, а не догадка о числе уже прочитанных.
        """
        page = _FakePage()
        page.cards = [_CardElement(number) for number in range(1, 89)]
        page.visible_count = 44
        parser = MegamarketParsePage(page)

        first = await parser.parse_current_page()
        page.visible_count = 88
        second = await parser.parse_current_page()

        self.assertEqual(len(first), 44)
        self.assertEqual(len(second), 88)
        self.assertEqual(second[0].title, "Товар 1")
        self.assertNotIn("Offset", page.evaluate_calls[-1])

    async def test_same_page_twice_yields_no_new_items(self):
        """Повтор той же страницы не даёт новых элементов, но и не падает."""
        page = _FakePage()
        page.cards = [_CardElement(number) for number in range(1, 45)]
        page.visible_count = 44
        parser = MegamarketParsePage(page)

        first = parser._only_new_items(await parser.parse_current_page())
        second = parser._only_new_items(await parser.parse_current_page())

        self.assertEqual(len(first), 44)
        self.assertEqual(second, [])

    async def test_raises_when_dom_has_cards_but_parse_yields_nothing(self):
        """Сломанная разметка — это ошибка, а не «выдача закончилась»."""
        page = _FakePage()
        page.cards = [_CardElement(number) for number in range(1, 45)]
        page.visible_count = 44
        page.broken_markup = True
        parser = MegamarketParsePage(page)

        with self.assertRaises(PageParseError) as caught:
            await parser.parse_current_page()

        self.assertIn("44", str(caught.exception))

    async def test_broken_markup_stops_run_and_marks_it_failed(self):
        """Прогон со сломанной разметкой помечается неудачным, а не штатным."""
        page = _FakePage()
        parser = MegamarketParsePage(
            page,
            number_pages=2,
            page_delay=0,
            cards_load_timeout=0.1,
            cards_poll_interval=0,
            cards_stable_checks=1,
        )
        page.broken_markup = True

        cards = await parser.parse("iphone")

        self.assertEqual(cards, [])
        self.assertTrue(parser.failed)

    async def test_successful_run_is_not_marked_failed(self):
        page = _FakePage()
        parser = MegamarketParsePage(
            page,
            number_pages=1,
            page_delay=0,
            cards_load_timeout=0.1,
            cards_poll_interval=0,
            cards_stable_checks=1,
        )

        cards = await parser.parse("iphone")

        self.assertEqual(len(cards), 3)
        self.assertFalse(parser.failed)

    async def test_stop_after_page_without_elements(self):
        page = _FakePage()
        parser = MegamarketParsePage(
            page,
            number_pages=None,
            page_delay=0,
            cards_load_timeout=0,
            cards_poll_interval=0,
            cards_stable_checks=1,
        )

        cards = await parser.parse("iphone")

        self.assertEqual(len(cards), 5)
        self.assertEqual(len(page.navigations), 3)
        self.assertIn("/catalog/page-3/", page.navigations[-1][0])

    async def test_navigation_timeout_falls_back_to_ready_probe(self):
        page = _FakePage()
        page.navigation_timeout = True
        parser = MegamarketParsePage(
            page,
            page_delay=0,
            url_settle_timeout=0,
            cards_load_timeout=0,
            cards_stable_checks=1,
        )
        parser._search_page_url = "https://megamarket.ru/catalog/?q=iphone"

        state = await parser._go_to_next_page(2)

        self.assertEqual(state.value, "ready")
        self.assertTrue(page.navigations[-1][1]["wait_load"])

    async def test_navigation_error_stops_before_parsing_next_page(self):
        page = _FakePage()
        parser = MegamarketParsePage(
            page,
            number_pages=2,
            page_delay=0,
            cards_load_timeout=0,
            cards_stable_checks=1,
        )
        original_navigate = page.navigate

        async def navigate(url: str, **kwargs):
            result = await original_navigate(url, **kwargs)
            if "/page-2/" in url:
                result["errorText"] = "net::ERR_FAILED"
            return result

        page.navigate = navigate

        cards = await parser.parse("iphone")

        self.assertEqual(len(cards), 3)


if __name__ == "__main__":
    unittest.main()
