from fastapi import APIRouter, HTTPException, Response

from megamarket.api.remote_deps import RemoteAuthDep
from megamarket.schemas.frontend import FrontendBundleInfo
from megamarket.services.frontend_bundle import (
    FrontendBundle,
    FrontendBundleMissing,
    get_frontend_bundle,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["remote-frontend"],
)


@router.get("/frontend", response_model=FrontendBundleInfo)
async def get_frontend_info(_: RemoteAuthDep) -> FrontendBundleInfo:
    bundle = _bundle()
    return FrontendBundleInfo(
        version=bundle.version,
        size=len(bundle.archive),
    )


@router.get("/frontend/bundle", response_model=None)
async def download_frontend_bundle(_: RemoteAuthDep) -> Response:
    bundle = _bundle()
    return Response(
        content=bundle.archive,
        media_type="application/gzip",
        headers={
            "ETag": f'"{bundle.version}"',
            "Content-Disposition": 'attachment; filename="frontend.tar.gz"',
        },
    )


def _bundle() -> FrontendBundle:
    try:
        return get_frontend_bundle()
    except FrontendBundleMissing as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
