import unittest

from parsing import MegamarketParsePage


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


class _CardElement:
    def __init__(self, number: int) -> None:
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
    DOM = object()


class _FakePage:
    def __init__(self) -> None:
        self.cdp = _CDP()
        self.cards = []
        self.visible_count = 0
        self.pending_counts = []
        self.current_url = "about:blank"
        self.navigations = []

    def domain_enabled(self, domain):
        return _DomainContext()

    async def navigate(self, url: str, **kwargs):
        self.current_url = url
        self.navigations.append((url, kwargs))
        if "/page-3/" in url:
            self.cards = []
            self.pending_counts = [0]
        elif "/page-2/" in url:
            self.cards = [_CardElement(number) for number in range(4, 6)]
            # Вторая страница содержит только свои товары и отрисовывает их
            # постепенно, а не дополняет товарами DOM первой страницы.
            self.pending_counts = [1, 2]
        else:
            self.cards = [_CardElement(number) for number in range(1, 4)]
            self.pending_counts = [3]

    async def wait_for_selector(self, *args, **kwargs):
        return object()

    async def evaluate(self, expression: str):
        if expression == "location.href":
            return self.current_url
        return ""

    async def select(self, *, selector: str):
        return None

    async def select_all(self, selector: str):
        if self.pending_counts:
            self.visible_count = self.pending_counts.pop(0)
        return list(self.cards[:self.visible_count])


class PaginationTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
