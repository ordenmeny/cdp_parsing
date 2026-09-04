from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import httpx
from fastapi import UploadFile

from megamarket.config import RemoteApiSettings
from megamarket.domain import SellerStatus
from megamarket.schemas.seller_jobs import (
    SellerJobFinishResponse,
    SellerJobStartResponse,
    SellerObservation,
    SellerObservationResponse,
)
from megamarket.schemas.sellers import SellerResponse, SellerUpdate


class RemoteApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


class RemoteApiUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RemoteFile:
    filename: str
    media_type: str
    content: bytes


class RemoteApiClient:
    def __init__(self, settings: RemoteApiSettings) -> None:
        self._client = httpx.AsyncClient(
            base_url=str(settings.remote_api_url).rstrip("/"),
            headers={
                "Authorization": (
                    "Bearer " + settings.remote_api_token.get_secret_value()
                )
            },
            timeout=httpx.Timeout(settings.remote_api_timeout),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_sellers(
            self,
            status: SellerStatus | None,
    ) -> list[SellerResponse]:
        params = {"status": status.value} if status is not None else None
        response = await self._request("GET", "/api/v1/sellers", params=params)
        return [SellerResponse.model_validate(item) for item in response.json()]

    async def set_sellers(
            self,
            updates: list[SellerUpdate],
    ) -> list[SellerResponse]:
        response = await self._request(
            "PATCH",
            "/api/v1/sellers",
            json=[update.model_dump(mode="json", exclude_unset=True) for update in updates],
        )
        return [SellerResponse.model_validate(item) for item in response.json()]

    async def start_job(
            self,
            *,
            limit: int,
            file: UploadFile | None,
    ) -> SellerJobStartResponse:
        files = None
        if file is not None:
            filename = Path(file.filename or "").name
            files = {
                "file": (
                    filename,
                    file.file,
                    file.content_type
                    or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
        try:
            response = await self._request(
                "POST",
                "/api/v1/seller-jobs",
                params={"limit": limit},
                files=files,
            )
        finally:
            if file is not None:
                await file.close()
        return SellerJobStartResponse.model_validate(response.json())

    async def observe(
            self,
            job_id: str,
            observation: SellerObservation,
    ) -> SellerObservationResponse:
        response = await self._request(
            "POST",
            f"/api/v1/seller-jobs/{job_id}/observations",
            json=observation.model_dump(mode="json"),
        )
        return SellerObservationResponse.model_validate(response.json())

    async def finish_job(
            self,
            job_id: str,
            stopped_reason: str,
    ) -> SellerJobFinishResponse:
        response = await self._request(
            "POST",
            f"/api/v1/seller-jobs/{job_id}/finish",
            json={"stopped_reason": stopped_reason},
        )
        return SellerJobFinishResponse.model_validate(response.json())

    async def download_job_file(self, job_id: str) -> RemoteFile:
        response = await self._request(
            "GET",
            f"/api/v1/seller-jobs/{job_id}/file",
        )
        filename = _response_filename(response) or "megamarket-sellers.xlsx"
        return RemoteFile(
            filename=filename,
            media_type=response.headers.get(
                "Content-Type",
                "application/octet-stream",
            ),
            content=response.content,
        )

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.RequestError as error:
            raise RemoteApiUnavailable(
                "Удалённое API недоступно"
            ) from error
        if response.is_error:
            detail = f"Ошибка удалённого API ({response.status_code})"
            try:
                payload = response.json()
                if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                    detail = payload["detail"]
            except ValueError:
                if response.text:
                    detail = response.text
            raise RemoteApiError(response.status_code, detail)
        return response


def _response_filename(response: httpx.Response) -> str | None:
    disposition = response.headers.get("Content-Disposition", "")
    for part in disposition.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key.casefold() == "filename*":
            encoded = value.split("''", 1)[-1]
            return unquote(encoded)
        if separator and key.casefold() == "filename":
            return value.strip('"')
    return None
