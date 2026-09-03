"""JS-экстракторы данных страницы, выполняемые одним Runtime.evaluate."""

from __future__ import annotations

import json
from dataclasses import dataclass


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True, slots=True)
class PageProbe:
    cards: int = 0
    not_found: bool = False
    block_marker: bool = False
    heading: str = ""
    ready_state: str = ""
    href: str = ""

    @classmethod
    def from_raw(cls, value: object) -> "PageProbe":
        if not isinstance(value, dict):
            return cls()
        return cls(
            cards=_non_negative_int(value.get("cards")),
            not_found=bool(value.get("notFound")),
            block_marker=bool(value.get("blockMarker")),
            heading=str(value.get("heading") or ""),
            ready_state=str(value.get("readyState") or ""),
            href=str(value.get("href") or ""),
        )


@dataclass(frozen=True, slots=True)
class ExtractedCard:
    index: int
    title: str
    price: str
    seller: str
    href: str
    image: str

    @classmethod
    def from_raw(cls, value: object) -> "ExtractedCard | None":
        if not isinstance(value, dict):
            return None
        try:
            index = int(value.get("index") or 0)
        except (TypeError, ValueError):
            return None
        return cls(
            index=index,
            title=str(value.get("title") or ""),
            price=str(value.get("price") or ""),
            seller=str(value.get("seller") or ""),
            href=str(value.get("href") or ""),
            image=str(value.get("image") or ""),
        )


@dataclass(frozen=True, slots=True)
class CardsExtraction:
    total: int
    offset: int
    items: tuple[ExtractedCard, ...]

    @classmethod
    def from_raw(cls, value: object) -> "CardsExtraction":
        if not isinstance(value, dict):
            return cls(total=0, offset=0, items=())
        total = _non_negative_int(value.get("total"))
        offset = _non_negative_int(value.get("offset"))
        raw_items = value.get("items")
        if not isinstance(raw_items, (list, tuple)):
            raw_items = ()
        items = tuple(
            card
            for raw_item in raw_items
            if (card := ExtractedCard.from_raw(raw_item)) is not None
        )
        return cls(total=total, offset=offset, items=items)


def build_page_probe_script(
        *,
        card_selector: str,
        not_found_selector: str,
        block_marker_selector: str,
) -> str:
    """Сформировать IIFE для единой проверки состояния страницы."""
    return r"""
(() => {
    const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const heading = document.querySelector('h1');
    return {
        cards: document.querySelectorAll(__CARD_SELECTOR__).length,
        notFound: Boolean(document.querySelector(__NOT_FOUND_SELECTOR__)),
        blockMarker: Boolean(document.querySelector(__BLOCK_MARKER_SELECTOR__)),
        heading: normalize(heading ? heading.textContent : ''),
        readyState: document.readyState || '',
        href: location.href || '',
    };
})()
""".replace("__CARD_SELECTOR__", json.dumps(card_selector)).replace(
        "__NOT_FOUND_SELECTOR__",
        json.dumps(not_found_selector),
    ).replace(
        "__BLOCK_MARKER_SELECTOR__",
        json.dumps(block_marker_selector),
    )


def build_cards_extractor_script(
        *,
        card_selector: str,
        title_selector: str,
        price_selector: str,
        seller_selector: str,
        image_selector: str,
        offset: int = 0,
) -> str:
    """Сформировать IIFE, возвращающий карточки одним JSON-ответом."""
    if offset < 0:
        raise ValueError("Смещение карточек не может быть отрицательным.")

    replacements = {
        "__CARD_SELECTOR__": card_selector,
        "__TITLE_SELECTOR__": title_selector,
        "__PRICE_SELECTOR__": price_selector,
        "__SELLER_SELECTOR__": seller_selector,
        "__IMAGE_SELECTOR__": image_selector,
    }
    script = r"""
(() => {
    const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const cards = Array.from(document.querySelectorAll(__CARD_SELECTOR__));
    const offset = Math.min(__OFFSET__, cards.length);
    const items = cards.slice(offset).map((card, localIndex) => {
        const title = card.querySelector(__TITLE_SELECTOR__);
        const price = card.querySelector(__PRICE_SELECTOR__);
        const seller = card.querySelector(__SELLER_SELECTOR__);
        const image = card.querySelector(__IMAGE_SELECTOR__);
        return {
            index: offset + localIndex,
            title: normalize(title ? title.textContent : ''),
            price: normalize(price ? price.textContent : ''),
            seller: normalize(seller ? seller.textContent : ''),
            href: title ? (title.getAttribute('href') || '') : '',
            image: image ? (image.getAttribute('content') || '') : '',
        };
    });
    return {total: cards.length, offset, items};
})()
""".replace("__OFFSET__", str(offset))
    for placeholder, selector in replacements.items():
        script = script.replace(placeholder, json.dumps(selector))
    return script


@dataclass(frozen=True, slots=True)
class SellerState:
    """Состояние страницы магазина, снятое одним ``Runtime.evaluate``."""

    ready: bool = False
    status_code: int = 0
    merchant_id: str = ""
    name: str = ""
    slug: str = ""
    official_name: str = ""
    ogrn: str = ""
    inn: str = ""
    email: str = ""
    phone: str = ""
    legal_form: str = ""
    address: str = ""
    rating: float | None = None

    @classmethod
    def from_raw(cls, value: object) -> "SellerState":
        if not isinstance(value, dict):
            return cls()

        def text(key: str) -> str:
            return str(value.get(key) or "").strip()

        try:
            status_code = int(value.get("statusCode") or 0)
        except (TypeError, ValueError):
            status_code = 0

        rating = value.get("rating")
        return cls(
            ready=bool(value.get("ready")),
            status_code=status_code,
            merchant_id=text("merchantId"),
            name=text("name"),
            slug=text("slug"),
            official_name=text("officialName"),
            ogrn=text("ogrn"),
            inn=text("inn"),
            email=text("email"),
            phone=text("phone"),
            legal_form=text("legalForm"),
            address=text("address"),
            rating=float(rating) if isinstance(rating, (int, float)) else None,
        )


# Магазин и его реквизиты SPA кладёт в состояние страницы, а несуществующий
# адрес отмечает там же кодом ответа. Поэтому обе проверки — один вызов, и
# разбирать вёрстку не нужно. Реквизиты дублируются во всплывающей подсказке
# у названия магазина, но она появляется только при наведении мыши.
SELLER_STATE_SCRIPT = r"""
(() => {
    const state = (window.__APP__ || {}).hydratorState || {};
    const error = (state.ApplicationStore || {}).serverError;
    const info = (state.MerchantStore || {}).merchantLegalInfo;
    const legal = (info && info.legalInfo) || {};
    return {
        ready: Boolean(window.__APP__),
        statusCode: error && error.statusCode ? error.statusCode : 0,
        merchantId: info ? String(info.id || '') : '',
        name: info ? String(info.name || '') : '',
        slug: info ? String(info.slug || '') : '',
        rating: info && typeof info.summaryRating === 'number'
            ? info.summaryRating
            : null,
        officialName: String((info && info.fullName) || legal.name || ''),
        // orgn — опечатка самого сайта; ogrn читаем на случай, если починят.
        ogrn: String(legal.orgn || legal.ogrn || ''),
        inn: String(legal.inn || ''),
        email: String(legal.email || ''),
        phone: String(legal.phone || ''),
        legalForm: String(legal.form || ''),
        address: String(legal.address || ''),
    };
})()
"""
