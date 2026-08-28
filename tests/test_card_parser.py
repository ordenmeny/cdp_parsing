import unittest

from domain import CardToPars, Stock
from parsing import MegamarketParseCard


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

    async def navigate(self, url: str, **kwargs) -> None:
        self.navigations.append((url, kwargs))

    async def wait_for_selector(self, selector: str, **kwargs):
        if selector == MegamarketParseCard.SELLER_LINK_SELECTOR:
            return self.link_element
        return self.seller_element

    async def select(self, *, selector: str):
        return self.seller_element

    async def evaluate(self, expression: str):
        return ""


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
        parser = MegamarketParseCard(_FakeCardPage(), [card])

        self.assertEqual(parser.get_cards(), [card])

    async def test_clicks_seller_and_reads_shop_link_from_modal(self):
        page = _FakeCardPage()
        card = self._card()
        parser = MegamarketParseCard(page, [card])

        result = await parser.parse(card)

        self.assertEqual(result, [card])
        self.assertEqual(page.seller_element.click_count, 1)
        self.assertEqual(
            card.seller_link,
            "https://megamarket.ru/shop/texno-edem/",
        )
        self.assertEqual(page.navigations[0][0], card.card_link)
        self.assertTrue(page.navigations[0][1]["wait_load"])

    async def test_opens_only_one_card_for_repeated_seller(self):
        page = _FakeCardPage()
        first = self._card(title="iphone-17")
        second = self._card(title="iphone-16")
        parser = MegamarketParseCard(page, [first, second], card_delay=0)

        cards = await parser.parse_all()

        self.assertEqual(len(page.navigations), 1)
        self.assertEqual(page.seller_element.click_count, 1)
        self.assertEqual(first.seller_link, second.seller_link)
        self.assertEqual(cards, [first, second])

    async def test_existing_link_is_preserved_and_reused_without_navigation(self):
        page = _FakeCardPage()
        empty = self._card(title="iphone-17")
        filled = self._card(title="iphone-16")
        filled.seller_link = "https://megamarket.ru/shop/existing-link/"
        parser = MegamarketParseCard(page, [empty, filled], card_delay=0)

        cards = await parser.parse_all()

        self.assertEqual(page.navigations, [])
        self.assertEqual(
            empty.seller_link,
            "https://megamarket.ru/shop/existing-link/",
        )
        self.assertEqual(
            filled.seller_link,
            "https://megamarket.ru/shop/existing-link/",
        )
        self.assertEqual(cards, [empty, filled])


if __name__ == "__main__":
    unittest.main()
