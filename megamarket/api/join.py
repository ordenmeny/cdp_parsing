import shutil
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from megamarket.services.join import join_reports


router = APIRouter(tags=["join"])


@router.post("/join", response_model=None)
async def join(
        files: Annotated[list[UploadFile], File()],
) -> FileResponse:
    try:
        result = await join_reports(files)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return FileResponse(
        result.output_path,
        filename=result.filename,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "X-Files-Joined": str(result.files_count),
            "X-Rows-Joined": str(result.rows_count),
        },
        # Временная папка живёт ровно до конца отдачи файла.
        background=BackgroundTask(
            shutil.rmtree,
            result.directory,
            ignore_errors=True,
        ),
    )
