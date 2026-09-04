import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from megamarket.api.remote_deps import (
    RemoteAuthDep,
    SellerJobServiceDep,
    SellerServiceDep,
)
from megamarket.api.workbooks import UploadedWorkbook
from megamarket.domain import SellerStatus
from megamarket.schemas.seller_jobs import (
    SellerJobFinishRequest,
    SellerJobFinishResponse,
    SellerJobStartResponse,
    SellerObservation,
    SellerObservationResponse,
)
from megamarket.schemas.sellers import SellerResponse, SellerUpdate
from megamarket.services.sellers import (
    SellerConflictError,
    SellerJobStateError,
    SellerNotFoundError,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["remote-sellers"],
)


@router.get("/sellers", response_model=list[SellerResponse])
async def get_sellers(
        _: RemoteAuthDep,
        service: SellerServiceDep,
        status: Annotated[SellerStatus | None, Query()] = None,
) -> list[SellerResponse]:
    sellers = await service.get_sellers(status)
    return [SellerResponse.model_validate(seller) for seller in sellers]


@router.patch("/sellers", response_model=list[SellerResponse])
async def set_sellers(
        updates: SellerUpdate | list[SellerUpdate],
        _: RemoteAuthDep,
        service: SellerServiceDep,
) -> list[SellerResponse]:
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


@router.post("/seller-jobs", response_model=SellerJobStartResponse)
async def start_seller_job(
        _: RemoteAuthDep,
        service: SellerJobServiceDep,
        limit: Annotated[int, Query(ge=1)] = 4,
        file: Annotated[UploadFile | None, File()] = None,
) -> SellerJobStartResponse:
    workbook: UploadedWorkbook | None = None
    try:
        if file is not None:
            workbook = await UploadedWorkbook.create(file)
        return await service.start(
            limit=limit,
            input_path=workbook.input_path if workbook else None,
            output_path=workbook.output_path if workbook else None,
            filename=workbook.filename if workbook else None,
        )
    except ValueError as error:
        if workbook is not None:
            workbook.cleanup()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception:
        if workbook is not None:
            workbook.cleanup()
        raise


@router.post(
    "/seller-jobs/{job_id}/observations",
    response_model=SellerObservationResponse,
)
async def observe_seller(
        job_id: str,
        observation: SellerObservation,
        _: RemoteAuthDep,
        service: SellerJobServiceDep,
) -> SellerObservationResponse:
    try:
        return await service.observe(job_id, observation)
    except SellerNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SellerJobStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except SellerConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/seller-jobs/{job_id}/finish",
    response_model=SellerJobFinishResponse,
)
async def finish_seller_job(
        job_id: str,
        request: SellerJobFinishRequest,
        _: RemoteAuthDep,
        service: SellerJobServiceDep,
) -> SellerJobFinishResponse:
    try:
        return await service.finish(
            job_id,
            stopped_reason=request.stopped_reason,
        )
    except SellerNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/seller-jobs/{job_id}/file", response_model=None)
async def get_seller_job_file(
        job_id: str,
        _: RemoteAuthDep,
        service: SellerJobServiceDep,
) -> FileResponse:
    try:
        path, filename = await service.get_file(job_id)
    except SellerNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SellerJobStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return FileResponse(
        path,
        filename=filename,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        background=BackgroundTask(_cleanup_job_directory, path),
    )


def _cleanup_job_directory(output_path: Path) -> None:
    directory = output_path.resolve().parents[1]
    temp_root = Path(tempfile.gettempdir()).resolve()
    if directory.parent == temp_root and directory.name.startswith(
        "define-sellers-"
    ):
        shutil.rmtree(directory, ignore_errors=True)
