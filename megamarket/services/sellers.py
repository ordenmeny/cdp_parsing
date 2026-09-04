from dataclasses import dataclass
from pathlib import Path

from parsek_cdp import Browser, ProtocolError
from parsek_cdp.core.target import Target
from sqlalchemy.exc import IntegrityError
from websockets.exceptions import ConnectionClosed

from megamarket.cdp.parsek_compat import install_parsek_target_race_fix
from megamarket.config import settings
from megamarket.db.models import Sellers, SellerStatus
from megamarket.exceptions import SiteBlocked
from megamarket.parsers.seller_page import MegamarketSellerPage, SellerPageState
from megamarket.repositories.sellers import SellerRepository
from megamarket.schemas.sellers import SellerUpdate
from megamarket.slug import SlugifyCard
from megamarket.storage.report import ExcelCardsReport
from megamarket.utils import normalize_link, normalize_text


@dataclass(frozen=True, slots=True)
class DefineSellersResult:
    added: int = 0
    selected: int = 0
    processed: int = 0
    confirmed: int = 0
    incorrect: int = 0
    unknown: int = 0
    stopped_reason: str = ""
    output_path: Path | None = None


class SellerBrowserUnavailable(RuntimeError):
    pass


class SellerNotFoundError(LookupError):
    pass


class SellerConflictError(RuntimeError):
    pass


class SellerService:
    def __init__(
            self,
            repository: SellerRepository,
            seller_page: MegamarketSellerPage | None = None,
    ) -> None:
        self.repository = repository
        self.seller_page = seller_page

    async def get_sellers(
            self,
            status: SellerStatus | None = None,
    ) -> list[Sellers]:
        return await self.repository.get_all(status)

    async def set_sellers(
            self,
            updates: list[SellerUpdate],
    ) -> list[Sellers]:
        sellers: list[Sellers] = []
        try:
            for update in updates:
                seller = await self.repository.get_by_identity(
                    seller_id=update.seller_id,
                    name=update.name,
                )
                if seller is None:
                    identity = update.seller_id or update.name
                    raise SellerNotFoundError(f"Продавец {identity!r} не найден")

                for field, value in update.changes().items():
                    setattr(seller, field, value)
                sellers.append(seller)

            await self.repository.flush()
            await self.repository.commit()
            return sellers
        except IntegrityError as error:
            await self.repository.rollback()
            raise SellerConflictError(
                "Изменения нарушают уникальность имени или ссылки продавца"
            ) from error
        except Exception:
            await self.repository.rollback()
            raise

    async def define_sellers(
            self,
            *,
            limit: int,
            input_path: Path | None = None,
            output_path: Path | None = None,
    ) -> DefineSellersResult:
        report: ExcelCardsReport | None = None
        added = 0
        browser: Browser | None = None

        try:
            if input_path is not None:
                if output_path is None:
                    raise ValueError("Не указан путь для выходного Excel-файла")
                report = ExcelCardsReport(input_path)
                added = await self.repository.add_new(
                    self._sellers_from_report(report)
                )
                await self.repository.commit()

            pending = await self.repository.get_unconfirmed(limit)
            processed = confirmed = incorrect = unknown = 0
            stopped_reason = ""

            if pending:
                parser, browser = await self._get_seller_page()
                for seller in pending:
                    try:
                        parsed = await parser.parse(seller.link_to_seller)
                    except SiteBlocked:
                        stopped_reason = "site_blocked"
                        break
                    except (ConnectionError, ConnectionClosed, ProtocolError):
                        stopped_reason = "browser_connection_lost"
                        break

                    processed += 1
                    if parsed.state is SellerPageState.NOT_FOUND:
                        await self.repository.mark_incorrect(seller.seller_id)
                        await self.repository.commit()
                        incorrect += 1
                    elif parsed.state is SellerPageState.FOUND and parsed.info is not None:
                        if parsed.info.seller_id != seller.seller_id:
                            await self.repository.mark_incorrect(seller.seller_id)
                            await self.repository.commit()
                            incorrect += 1
                            continue

                        canonical_link = (
                            f"{settings.base_url}/shop/{parsed.info.slug}/"
                            if parsed.info.slug
                            else seller.link_to_seller
                        )
                        await self.repository.confirm(
                            seller.seller_id,
                            parsed.info,
                            canonical_link,
                        )
                        await self.repository.commit()
                        confirmed += 1
                    else:
                        unknown += 1

            saved_path = None
            if report is not None and output_path is not None:
                await self._set_report_links(report)
                saved_path = report.save(
                    output_path,
                    replace_seller_links=True,
                )

            return DefineSellersResult(
                added=added,
                selected=len(pending),
                processed=processed,
                confirmed=confirmed,
                incorrect=incorrect,
                unknown=unknown,
                stopped_reason=stopped_reason,
                output_path=saved_path,
            )
        finally:
            if report is not None:
                report.close()
            if browser is not None:
                try:
                    # Browser.close() завершает сам Chrome. Нам нужно закрыть
                    # только CDP-соединения API-процесса.
                    await Target.close(browser)
                except (ConnectionError, ConnectionClosed, ProtocolError):
                    pass

    @staticmethod
    def _sellers_from_report(report: ExcelCardsReport) -> list[Sellers]:
        sellers: list[Sellers] = []
        for card in report.cards:
            name = normalize_text(card.seller)
            sellers.append(
                Sellers(
                    seller_id=normalize_link(card.card_link),
                    name=name,
                    link_to_seller=SlugifyCard.link_for_seller(name),
                    link_to_card=card.card_link,
                    status=SellerStatus.UNCONFIRMED,
                )
            )
        return sellers

    async def _set_report_links(self, report: ExcelCardsReport) -> None:
        seller_ids = {
            normalize_link(card.card_link)
            for card in report.cards
        }
        sellers = await self.repository.get_by_ids(seller_ids)
        for card in report.cards:
            seller = sellers.get(normalize_link(card.card_link))
            card.seller_link = (
                seller.link_to_seller
                if seller is not None and seller.status is SellerStatus.CORRECT
                else ""
            )

    async def _get_seller_page(self) -> tuple[MegamarketSellerPage, Browser | None]:
        if self.seller_page is not None:
            return self.seller_page, None

        install_parsek_target_race_fix()
        try:
            browser = await Browser.connect_http(settings.browser_endpoint)
        except Exception as error:
            raise SellerBrowserUnavailable(
                f"Не удалось подключиться к браузеру: {settings.browser_endpoint}"
            ) from error
        return MegamarketSellerPage(browser), browser
