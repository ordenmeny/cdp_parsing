import unittest
from unittest.mock import AsyncMock, MagicMock

from megamarket.cdp.extractors import ClickPoint
from megamarket.parsers.parsing import is_product_page_url
from megamarket.parsers.scrolling import MegamarketScrollPage


LISTING_URL = "https://megamarket.ru/catalog/makita/page-4/"
PRODUCT_URL = (
    "https://megamarket.ru/catalog/details/"
    "elektroinstrument-makita-ddf485rfj-600004746195/"
)


def make_page():
    page = MagicMock()
    page.cdp.Input.dispatch_mouse_event = AsyncMock()
    return page


def make_parser():
    parser = MegamarketScrollPage(make_page())
    # Промахи в тестах отрабатываются мгновенно.
    parser.CLICK_SETTLE_DELAY = 0
    return parser


def make_element(*points: dict):
    element = MagicMock()
    element.apply = AsyncMock(side_effect=list(points))
    return element


def probe(href: str, cards: int = 96):
    return MagicMock(cards=cards, href=href, heading="")


class ProductPageUrlTests(unittest.TestCase):
    def test_card_links_are_recognised(self):
        self.assertTrue(is_product_page_url(PRODUCT_URL))
        self.assertTrue(
            is_product_page_url(
                "https://megamarket.ru/promo-page/details/#?slug=item_1"
            )
        )

    def test_listing_urls_are_not_product_pages(self):
        for url in (
            LISTING_URL,
            "https://megamarket.ru/catalog/?q=makita",
            "https://megamarket.ru/brands/makita/",
            "",
        ):
            self.assertFalse(is_product_page_url(url), url)


class ClickPointTests(unittest.TestCase):
    def test_missing_or_broken_answer_is_not_clickable(self):
        for raw in (None, "нет", {}, {"x": "далеко", "y": 1, "ok": True}):
            self.assertFalse(ClickPoint.from_raw(raw).ok, raw)


class ClickElementTests(unittest.IsolatedAsyncioTestCase):
    async def test_click_lands_on_the_verified_point(self):
        parser = make_parser()
        element = make_element({"x": 761.0, "y": 360.0, "ok": True, "hit": "button"})

        self.assertTrue(await parser._click_element(element, "кнопку"))

        dispatch = parser.page.cdp.Input.dispatch_mouse_event
        self.assertEqual(
            [call.kwargs["type_"] for call in dispatch.await_args_list],
            ["mouseMoved", "mousePressed", "mouseReleased"],
        )
        for call in dispatch.await_args_list:
            self.assertEqual((call.kwargs["x"], call.kwargs["y"]), (761.0, 360.0))

    async def test_occupied_point_is_re_aimed_instead_of_clicked(self):
        parser = make_parser()
        # Первый замер попадает в карточку — по ней кликать нельзя.
        element = make_element(
            {"x": 761.0, "y": 360.0, "ok": False, "hit": "a.catalog-item-image-block"},
            {"x": 761.0, "y": 402.0, "ok": True, "hit": "button"},
        )

        self.assertTrue(await parser._click_element(element, "кнопку"))

        dispatch = parser.page.cdp.Input.dispatch_mouse_event
        self.assertEqual(dispatch.await_count, 3)
        # Нажатие ушло по второй, проверенной точке.
        for call in dispatch.await_args_list:
            self.assertEqual(call.kwargs["y"], 402.0)

    async def test_click_is_skipped_when_aiming_keeps_failing(self):
        parser = make_parser()
        miss = {"x": 1.0, "y": 2.0, "ok": False, "hit": "a.catalog-item-image-block"}
        element = make_element(*[miss] * parser.CLICK_ATTEMPTS)

        self.assertFalse(await parser._click_element(element, "кнопку"))

        parser.page.cdp.Input.dispatch_mouse_event.assert_not_awaited()
        self.assertEqual(element.apply.await_count, parser.CLICK_ATTEMPTS)


class ScrollSettleTests(unittest.IsolatedAsyncioTestCase):
    async def test_wheel_scroll_is_awaited_until_it_stops(self):
        parser = make_parser()
        parser.SCROLL_SETTLE_INTERVAL = 0
        # Колесо докручивается плавно: позиция меняется ещё пару проверок.
        parser.page.evaluate = AsyncMock(side_effect=[1200, 1800, 2400, 2400])

        await parser._wait_scroll_settled()

        self.assertEqual(parser.page.evaluate.await_count, 4)

    async def test_scrolling_ends_with_a_settled_page(self):
        parser = make_parser()
        parser.SCROLL_STEP_DELAY = 0
        parser._wait_scroll_settled = AsyncMock()

        await parser._scroll_down()

        self.assertEqual(
            parser.page.cdp.Input.dispatch_mouse_event.await_count,
            parser.SCROLL_STEPS,
        )
        parser._wait_scroll_settled.assert_awaited_once_with()


class LoadMoreTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _prepared(parser):
        parser._find_more_button = AsyncMock(return_value=MagicMock())
        parser._sleep_before_more = AsyncMock()
        parser._scroll_down = AsyncMock()
        parser._wait_cards_grew = AsyncMock(return_value=True)
        return parser

    async def test_normal_click_loads_the_next_portion(self):
        parser = self._prepared(make_parser())
        parser._click_element = AsyncMock(return_value=True)
        parser._probe_page = AsyncMock(
            side_effect=[probe(LISTING_URL), probe(LISTING_URL)]
        )

        self.assertTrue(await parser._load_more(0))
        self.assertFalse(parser.left_listing)
        parser._wait_cards_grew.assert_awaited_once_with(96)

    async def test_opened_product_card_stops_the_run(self):
        parser = self._prepared(make_parser())
        parser._click_element = AsyncMock(return_value=True)
        parser._probe_page = AsyncMock(
            side_effect=[probe(LISTING_URL), probe(PRODUCT_URL, cards=0)]
        )

        self.assertFalse(await parser._load_more(0))
        self.assertTrue(parser.left_listing)
        # Ждать прироста на карточке товара незачем — это 30 секунд впустую.
        parser._wait_cards_grew.assert_not_awaited()

    async def test_failed_aiming_stops_before_clicking_anything(self):
        parser = self._prepared(make_parser())
        parser._click_element = AsyncMock(return_value=False)
        parser._probe_page = AsyncMock(return_value=probe(LISTING_URL))

        self.assertFalse(await parser._load_more(0))
        parser._wait_cards_grew.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
