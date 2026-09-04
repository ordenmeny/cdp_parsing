from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from megamarket.api.deps import SellerServiceDep
from megamarket.api.workbooks import UploadedWorkbook
from megamarket.db.models import SellerStatus
from megamarket.schemas.sellers import (
    DefineSellersResponse,
    SellerResponse,
    SellerUpdate,
)
from megamarket.services.sellers import (
    SellerBrowserUnavailable,
    SellerConflictError,
    SellerNotFoundError,
)

router = APIRouter(tags=["sellers"])


@router.get("/get_sellers", response_model=list[SellerResponse])
async def get_sellers(
        service: SellerServiceDep,
        status: Annotated[SellerStatus | None, Query()] = None,
) -> list[SellerResponse]:
    """
    Ендпоинт для получения селлеров по их статусу.
    correct - ссылка на продавца верная.
    incorrect - ссылка неверная
    unconfirmed - ссылка на продавца еще не проверена, для проверки есть ендпоинт define_sellers
    """
    sellers = await service.get_sellers(status)
    return [SellerResponse.model_validate(seller) for seller in sellers]


@router.patch("/set_sellers", response_model=list[SellerResponse])
async def set_sellers(
        updates: SellerUpdate | list[SellerUpdate],
        service: SellerServiceDep,
) -> list[SellerResponse]:
    """
    Ендпоинт для изменения данных о конкретном продавце.
    Передайте либо name, либо seller_id и поля для изменения.
    """
    items = updates if isinstance(updates, list) else [updates]
    if not items:
        raise HTTPException(status_code=422, detail="Список изменений пуст")

    try:
        sellers = await service.set_sellers(items)
    except SellerNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SellerConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return [SellerResponse.model_validate(seller) for seller in sellers]


@router.post("/define_sellers", response_model=None)
async def define_sellers(
        service: SellerServiceDep,
        limit: Annotated[int, Query(ge=1)] = 4,
        file: Annotated[UploadFile | None, File()] = None,
) -> DefineSellersResponse | FileResponse:
    """
    Функция для автоматического подтверждения продавцов (а точнее их ссылок и данных).
    Можно вставить файл и в базу данных будут загружены новые продавцы со статусом unconfirmed.
    limit - параметр, отвечающий за то, сколько будет подтверждено продавцов за одно исполнение функции.
    Результатом исполнения функции будет изменение статусов продавцов на incorrect или correct.
    В случае верной ссылки будет установлен статус correct и будут собраны данные о продавце.
    Статус incorrect означает, что текущая ссылка на продавца некорректна.
    """
    workbook: UploadedWorkbook | None = None
    try:
        if file is not None:
            workbook = await UploadedWorkbook.create(file)
        result = await service.define_sellers(
            limit=limit,
            input_path=workbook.input_path if workbook else None,
            output_path=workbook.output_path if workbook else None,
        )
    except ValueError as error:
        if workbook is not None:
            workbook.cleanup()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SellerBrowserUnavailable as error:
        if workbook is not None:
            workbook.cleanup()
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception:
        if workbook is not None:
            workbook.cleanup()
        raise

    payload = asdict(result)
    payload.pop("output_path")
    if workbook is None:
        return DefineSellersResponse.model_validate(payload)

    if result.output_path is None:
        workbook.cleanup()
        raise HTTPException(status_code=500, detail="Выходной файл не был создан")

    headers = {
        f"X-Sellers-{name.replace('_', '-').title()}": str(value)
        for name, value in payload.items()
    }
    return FileResponse(
        result.output_path,
        filename=workbook.filename,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers=headers,
        background=BackgroundTask(workbook.cleanup),
    )
