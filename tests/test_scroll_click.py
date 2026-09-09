import unittest
from unittest.mock import AsyncMock, MagicMock

from parsek_cdp import ProtocolError

from megamarket.cdp.extractors import ClickPoint, PageProbe
from megamarket.domain import CardToPars
from megamarket.parsers.base_parser import PageState
from megamarket.parsers.parsing import BLOCKED_HEADING, is_product_page_url
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
    """Элемент, чьё прицеливание отвечает заданными точками по очереди."""
    element = MagicMock()
    element.backend_id = 42
    element._points = list(points)
    return element


def aiming(parser, element):
    """Подменить обмен с браузером ответами, заданными в элементе."""

    async def _aim(target):
        assert target is element
        return ClickPoint.from_raw(element._points.pop(0))

    parser._aim_at = AsyncMock(side_effect=_aim)
    return parser._aim_at


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
        aiming(parser, element)

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
        aiming(parser, element)

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
        aim = aiming(parser, element)

        self.assertFalse(await parser._click_element(element, "кнопку"))

        parser.page.cdp.Input.dispatch_mouse_event.assert_not_awaited()
        self.assertEqual(aim.await_count, parser.CLICK_ATTEMPTS)


class AimAtTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _parser(resolve, call=None):
        parser = make_parser()
        parser.page.domain_enabled = MagicMock(return_value=_enabled())
        parser.page.cdp.DOM.resolve_node = resolve
        parser.page.cdp.Runtime.call_function_on = call or AsyncMock()
        return parser

    async def test_node_is_resolved_with_the_dom_domain_enabled(self):
        # backendNodeId переживает выключение домена, а nodeId — нет: на этом
        # прицеливание и спотыкалось.
        resolve = AsyncMock(
            return_value=MagicMock(object=MagicMock(object_id="obj-1"))
        )
        call = AsyncMock(
            return_value=MagicMock(
                result=MagicMock(value={"x": 5.0, "y": 6.0, "ok": True, "hit": "button"})
            )
        )
        parser = self._parser(resolve, call)
        element = MagicMock(backend_id=42)

        point = await parser._aim_at(element)

        self.assertTrue(point.ok)
        self.assertEqual((point.x, point.y), (5.0, 6.0))
        parser.page.domain_enabled.assert_called_once_with(parser.page.cdp.DOM)
        resolve.assert_awaited_once_with(backend_node_id=42)

    async def test_stale_node_is_reported_instead_of_breaking_the_run(self):
        parser = self._parser(
            AsyncMock(side_effect=ProtocolError(-32000, "No node with given id found"))
        )

        point = await parser._aim_at(MagicMock(backend_id=42))

        self.assertFalse(point.ok)
        parser.page.cdp.Runtime.call_function_on.assert_not_awaited()


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


class _enabled:
    """Заглушка ``page.domain_enabled`` — обычный асинхронный контекст."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, *_):
        return False


class CaptchaTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _probes(*probes):
        return AsyncMock(side_effect=list(probes))

    @staticmethod
    def _blocked(cards: int = 0):
        return PageProbe(cards=cards, heading=f"  {BLOCKED_HEADING.title()}  ")

    async def test_page_waits_until_the_check_is_solved_by_hand(self):
        parser = make_parser()
        parser.cards_poll_interval = 0
        # Заглушка держится две проверки, затем человек решает капчу.
        parser._probe_page = self._probes(
            self._blocked(),
            self._blocked(),
            PageProbe(cards=48),
        )
        parser.wait_content_ready = AsyncMock()

        self.assertIs(await parser.wait_page_state(), PageState.READY)
        self.assertEqual(parser._probe_page.await_count, 3)

    async def test_unsolved_check_gives_up_after_the_timeout(self):
        parser = make_parser()
        parser.cards_poll_interval = 0
        parser.captcha_timeout = 0
        parser._probe_page = AsyncMock(return_value=self._blocked())

        self.assertIs(await parser.wait_page_state(), PageState.BLOCKED)

    async def test_solved_check_lets_the_run_continue(self):
        parser = make_parser()
        parser._find_more_button = AsyncMock(return_value=MagicMock())
        parser._sleep_before_more = AsyncMock()
        parser._scroll_down = AsyncMock()
        parser._click_element = AsyncMock(return_value=True)
        parser._left_the_listing = AsyncMock(return_value=False)
        parser._wait_cards_grew = AsyncMock(return_value=False)
        parser._probe_page = self._probes(PageProbe(cards=96), self._blocked())
        parser.wait_page_state = AsyncMock(return_value=PageState.READY)

        self.assertTrue(await parser._load_more(0))
        self.assertTrue(parser.captcha_recovered)

    @staticmethod
    def _run_with_reloaded_page(parser, recover: bool):
        """Прогон, где вторая итерация видит ту же страницу, что и первая."""
        card = CardToPars(
            title="Дрель",
            price="100 ₽",
            seller="Кувалда",
            card_link="https://megamarket.ru/catalog/details/a_1/",
        )
        parser.repeat_pages_limit = 1
        parser._open_search = AsyncMock(return_value=PageState.READY)
        parser.prepare_first_page = AsyncMock(return_value=PageState.READY)
        parser._parse_current_page_measured = AsyncMock(
            side_effect=[[card], [card], [card]]
        )

        async def load_more(clicks: int) -> bool:
            if clicks == 0:
                parser.captcha_recovered = recover
                return True
            return False

        parser._load_more = AsyncMock(side_effect=load_more)
        return parser

    async def test_page_returned_after_the_check_is_not_a_ring(self):
        parser = self._run_with_reloaded_page(make_parser(), recover=True)

        await parser.parse("makita")

        # Дошли до второй догрузки: повтор после проверки кольцом не сочли.
        self.assertEqual(parser._load_more.await_count, 2)
        self.assertFalse(parser.captcha_recovered)

    async def test_same_page_without_a_check_still_stops_the_ring(self):
        parser = self._run_with_reloaded_page(make_parser(), recover=False)

        await parser.parse("makita")

        # Без проверки повтор остаётся признаком кольца — сбор прекращается.
        self.assertEqual(parser._load_more.await_count, 1)


if __name__ == "__main__":
    unittest.main()
