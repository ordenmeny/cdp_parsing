import unittest
from unittest.mock import AsyncMock, call, patch

from megamarket.domain import CardToPars, Stock
from megamarket.parsers.parsing import MegamarketParseCard


class _SellerElement:
    def __init__(self) -> None:
        self.click_count = 0

    async def mouse_click(self) -> None:
        self.click_count += 1


class _LinkElement:
    attributes = {"href": "https://megamarket.ru/shop/texno-edem/offers/"}


class _FakeCardPage:
    def __init__(self) -> None:
        self.seller_element = _SellerElement()
        self.link_element = _LinkElement()
        self.navigations = []
        self.cdp = type("CDP", (), {})()
        self.cdp.Page = type("PageDomain", (), {})()
        self.cdp.Page.close = AsyncMock()

    async def navigate(self, url: str, **kwargs) -> None:
        self.navigations.append((url, kwargs))

    async def wait_for_selector(self, selector: str, **kwargs):
        if selector == MegamarketParseCard.SELLER_LINK_SELECTOR:
            return self.link_element
        return self.seller_element

    async def select(self, *, selector: str):
        return self.seller_element

    async def evaluate(self, expression: str):
        if MegamarketParseCard.MERCHANT_NAME_SELECTOR in expression:
            return "TEXNO EDEM"
        return ""


class _FakeBrowser:
    def __init__(self, page_factory=_FakeCardPage) -> None:
        self.pages: list[_FakeCardPage] = []
        self.page_factory = page_factory

    async def new_page(self) -> _FakeCardPage:
        page = self.page_factory()
        self.pages.append(page)
        return page


class _ManuallyClosedPage(_FakeCardPage):
    def __init__(self) -> None:
        super().__init__()
        self.cdp.Page.close.side_effect = ConnectionError("CDP connection closed")

    async def navigate(self, url: str, **kwargs) -> None:
        self.navigations.append((url, kwargs))
        raise ConnectionError("CDP connection closed")


class CardParserTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _card(*, title: str = "iPhone", merchant_id: int = 251786) -> CardToPars:
        return CardToPars(
            title=title,
            price="224 563 ₽",
            seller="TEXNO EDEM",
            card_link=(
                "https://megamarket.ru/promo-page/details/"
                f"#?slug={title}_{merchant_id}&merchantId={merchant_id}&"
                f"exclusiveMerchantId={merchant_id}"
            ),
            stock=Stock.IN_STOCK,
        )

    def test_get_cards_returns_input_cards(self):
        card = self._card()
        parser = MegamarketParseCard(_FakeBrowser(), [card])

        self.assertEqual(parser.get_cards(), [card])

    async def test_clicks_seller_and_reads_shop_link_from_modal(self):
        browser = _FakeBrowser()
        card = self._card()
        parser = MegamarketParseCard(
            browser,
            [card],
            card_delay=0,
            card_close_delay=0,
        )

        result = await parser.parse(card)
        page = browser.pages[0]

        self.assertEqual(result, [card])
        self.assertEqual(page.seller_element.click_count, 1)
        self.assertEqual(
            card.seller_link,
            "https://megamarket.ru/shop/texno-edem/",
        )
        self.assertEqual(page.navigations[0][0], card.card_link)
        self.assertFalse(page.navigations[0][1]["wait_load"])
        page.cdp.Page.close.assert_awaited_once_with()

    async def test_opens_only_one_card_for_repeated_seller(self):
        browser = _FakeBrowser()
        first = self._card(title="iphone-17")
        second = self._card(title="iphone-16")
        parser = MegamarketParseCard(
            browser,
            [first, second],
            card_delay=0,
            card_close_delay=0,
        )

        cards = await parser.parse_all()
        page = browser.pages[0]

        self.assertEqual(len(browser.pages), 1)
        self.assertEqual(len(page.navigations), 1)
        self.assertEqual(page.seller_element.click_count, 1)
        page.cdp.Page.close.assert_awaited_once_with()
        self.assertEqual(first.seller_link, second.seller_link)
        self.assertEqual(cards, [first, second])

    async def test_existing_link_is_preserved_and_reused_without_navigation(self):
        browser = _FakeBrowser()
        empty = self._card(title="iphone-17")
        filled = self._card(title="iphone-16")
        filled.seller_link = "https://megamarket.ru/shop/existing-link/"
        parser = MegamarketParseCard(
            browser,
            [empty, filled],
            card_delay=0,
            card_close_delay=0,
        )

        cards = await parser.parse_all()

        self.assertEqual(browser.pages, [])
        self.assertEqual(
            empty.seller_link,
            "https://megamarket.ru/shop/existing-link/",
        )
        self.assertEqual(
            filled.seller_link,
            "https://megamarket.ru/shop/existing-link/",
        )
        self.assertEqual(cards, [empty, filled])

    async def test_waits_before_each_real_card_navigation(self):
        browser = _FakeBrowser()
        first = self._card(title="iphone-17", merchant_id=1)
        second = self._card(title="iphone-16", merchant_id=2)
        parser = MegamarketParseCard(
            browser,
            [first, second],
            card_delay=7,
            card_close_delay=3,
        )

        with patch("megamarket.parsers.parsing.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await parser.parse_all()

        self.assertEqual(len(browser.pages), 2)
        self.assertTrue(all(len(page.navigations) == 1 for page in browser.pages))
        for page in browser.pages:
            page.cdp.Page.close.assert_awaited_once_with()
        self.assertEqual(
            sleep.await_args_list,
            [call(7), call(3), call(7), call(3)],
        )

    async def test_manual_tab_close_stops_without_losing_collected_cards(self):
        browser = _FakeBrowser(_ManuallyClosedPage)
        first = self._card(title="iphone-17", merchant_id=1)
        second = self._card(title="iphone-16", merchant_id=2)
        parser = MegamarketParseCard(
            browser,
            [first, second],
            card_delay=0,
            card_close_delay=3,
        )

        cards = await parser.parse_all()

        self.assertEqual(cards, [first, second])
        self.assertEqual(len(browser.pages), 1)
        # Вкладка уже закрыта оператором: повторный Page.close не отправляем.
        browser.pages[0].cdp.Page.close.assert_not_awaited()
        self.assertEqual(first.seller_link, "")
        self.assertEqual(second.seller_link, "")


if __name__ == "__main__":
    unittest.main()
