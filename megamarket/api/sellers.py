from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile

from megamarket.api.deps import LocalSellerServiceDep
from megamarket.clients.remote_api import RemoteApiError, RemoteApiUnavailable
from megamarket.domain import SellerStatus
from megamarket.schemas.sellers import (
    DefineSellersResponse,
    SellerResponse,
    SellerUpdate,
)


router = APIRouter(tags=["sellers"])


@router.get("/get_sellers", response_model=list[SellerResponse])
async def get_sellers(
        service: LocalSellerServiceDep,
        status: Annotated[SellerStatus | None, Query()] = None,
) -> list[SellerResponse]:
    try:
        return await service.get_sellers(status)
    except (RemoteApiError, RemoteApiUnavailable) as error:
        raise _http_error(error) from error


@router.patch("/set_sellers", response_model=list[SellerResponse])
async def set_sellers(
        updates: SellerUpdate | list[SellerUpdate],
        service: LocalSellerServiceDep,
) -> list[SellerResponse]:
    items = updates if isinstance(updates, list) else [updates]
    if not items:
        raise HTTPException(status_code=422, detail="Список изменений пуст")
    try:
        return await service.set_sellers(items)
    except (RemoteApiError, RemoteApiUnavailable) as error:
        raise _http_error(error) from error


@router.post("/define_sellers", response_model=None)
async def define_sellers(
        service: LocalSellerServiceDep,
        limit: Annotated[int, Query(ge=1)] = 4,
        file: Annotated[UploadFile | None, File()] = None,
) -> DefineSellersResponse | Response:
    try:
        result = await service.define_sellers(limit=limit, file=file)
    except (RemoteApiError, RemoteApiUnavailable) as error:
        raise _http_error(error) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    summary = result.summary
    if result.file is None:
        return DefineSellersResponse(
            added=summary.added,
            selected=summary.selected,
            processed=summary.processed,
            confirmed=summary.confirmed,
            incorrect=summary.incorrect,
            unknown=summary.unknown,
            stopped_reason=summary.stopped_reason,
        )

    headers = {
        "Content-Disposition": (
            "attachment; filename*=UTF-8''" + quote(result.file.filename)
        ),
        "X-Sellers-Added": str(summary.added),
        "X-Sellers-Selected": str(summary.selected),
        "X-Sellers-Processed": str(summary.processed),
        "X-Sellers-Confirmed": str(summary.confirmed),
        "X-Sellers-Incorrect": str(summary.incorrect),
        "X-Sellers-Unknown": str(summary.unknown),
    }
    return Response(
        content=result.file.content,
        media_type=result.file.media_type,
        headers=headers,
    )


def _http_error(error: RemoteApiError | RemoteApiUnavailable) -> HTTPException:
    if isinstance(error, RemoteApiError):
        return HTTPException(status_code=error.status_code, detail=str(error))
    return HTTPException(status_code=503, detail=str(error))
