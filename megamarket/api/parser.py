from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from megamarket.api.deps import ParserServiceDep
from megamarket.schemas.parser import ParseRequest
from megamarket.services.parser import (
    InvalidParseCommand,
    ParserBrowserUnavailable,
)


router = APIRouter(tags=["parser"])


@router.post("/parse", response_model=None)
async def parse(
        request: ParseRequest,
        service: ParserServiceDep,
) -> FileResponse:
    try:
        result = await service.parse(request.command)
    except InvalidParseCommand as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ParserBrowserUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return FileResponse(
        result.output_path,
        filename=result.output_path.name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"X-Cards-Collected": str(result.cards_count)},
    )
