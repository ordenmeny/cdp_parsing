import hmac
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from megamarket.config import get_remote_api_auth_settings
from megamarket.db.deps import AsyncSessionDep
from megamarket.repositories.sellers import SellerRepository
from megamarket.services.sellers import SellerJobService, SellerService


bearer = HTTPBearer(auto_error=False)


def verify_remote_token(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer),
        ],
) -> None:
    expected = (
        get_remote_api_auth_settings().remote_api_token.get_secret_value()
    )
    supplied = credentials.credentials if credentials is not None else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Неверный API-токен")


RemoteAuthDep = Annotated[None, Depends(verify_remote_token)]


def get_seller_service(session: AsyncSessionDep) -> SellerService:
    return SellerService(SellerRepository(session))


def get_seller_job_service(session: AsyncSessionDep) -> SellerJobService:
    return SellerJobService(SellerRepository(session))


SellerServiceDep = Annotated[SellerService, Depends(get_seller_service)]
SellerJobServiceDep = Annotated[SellerJobService, Depends(get_seller_job_service)]
