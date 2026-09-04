from dataclasses import dataclass

from fastapi import UploadFile
from parsek_cdp import Browser, ProtocolError
from parsek_cdp.core.target import Target
from websockets.exceptions import ConnectionClosed

from megamarket.cdp.parsek_compat import install_parsek_target_race_fix
from megamarket.cdp.browser_endpoint import connect_browser
from megamarket.clients.remote_api import RemoteApiClient, RemoteFile
from megamarket.config import settings
from megamarket.domain import SellerObservationState, SellerStatus
from megamarket.exceptions import SiteBlocked
from megamarket.parsers.seller_page import MegamarketSellerPage, SellerPageState
from megamarket.schemas.seller_jobs import (
    SellerJobFinishResponse,
    SellerObservation,
)
from megamarket.schemas.sellers import SellerResponse, SellerUpdate


@dataclass(frozen=True, slots=True)
class LocalDefineResult:
    summary: SellerJobFinishResponse
    file: RemoteFile | None


class LocalSellerService:
    """Локальный оркестратор: удалённое API плюс Chrome пользователя."""

    def __init__(self, remote: RemoteApiClient) -> None:
        self.remote = remote

    async def get_sellers(
            self,
            status: SellerStatus | None,
    ) -> list[SellerResponse]:
        return await self.remote.get_sellers(status)

    async def set_sellers(
            self,
            updates: list[SellerUpdate],
    ) -> list[SellerResponse]:
        return await self.remote.set_sellers(updates)

    async def define_sellers(
            self,
            *,
            limit: int,
            file: UploadFile | None,
    ) -> LocalDefineResult:
        job = await self.remote.start_job(limit=limit, file=file)
        stopped_reason = ""
        browser: Browser | None = None
        try:
            if job.sellers:
                try:
                    browser = await self._connect_browser()
                except RuntimeError:
                    stopped_reason = "browser_unavailable"
                else:
                    parser = MegamarketSellerPage(browser)
                    for seller in job.sellers:
                        try:
                            parsed = await parser.parse(seller.link_to_seller)
                        except SiteBlocked:
                            stopped_reason = "site_blocked"
                            break
                        except (ConnectionError, ConnectionClosed, ProtocolError):
                            stopped_reason = "browser_connection_lost"
                            break

                        if parsed.state is SellerPageState.FOUND:
                            observation = SellerObservation(
                                seller_id=seller.seller_id,
                                state=SellerObservationState.FOUND,
                                info=parsed.info,
                            )
                        elif parsed.state is SellerPageState.NOT_FOUND:
                            observation = SellerObservation(
                                seller_id=seller.seller_id,
                                state=SellerObservationState.NOT_FOUND,
                            )
                        else:
                            observation = SellerObservation(
                                seller_id=seller.seller_id,
                                state=SellerObservationState.UNKNOWN,
                            )
                        await self.remote.observe(job.job_id, observation)
        except Exception:
            stopped_reason = stopped_reason or "local_error"
            raise
        finally:
            if browser is not None:
                try:
                    await Target.close(browser)
                except (ConnectionError, ConnectionClosed, ProtocolError):
                    pass
            summary = await self.remote.finish_job(job.job_id, stopped_reason)

        output = (
            await self.remote.download_job_file(job.job_id)
            if summary.has_file
            else None
        )
        return LocalDefineResult(summary=summary, file=output)

    @staticmethod
    async def _connect_browser() -> Browser:
        install_parsek_target_race_fix()
        try:
            return await connect_browser(settings.browser_endpoint)
        except Exception as error:
            raise RuntimeError(
                f"Не удалось подключиться к браузеру: {settings.browser_endpoint}"
            ) from error
