from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

from megamarket.clients.remote_api import RemoteApiClient
from megamarket.config import get_remote_api_settings
from megamarket.services.local_sellers import LocalSellerService
from megamarket.services.parser import ParserService


def get_parser_service() -> ParserService:
    return ParserService()


async def get_remote_api_client() -> AsyncIterator[RemoteApiClient]:
    client = RemoteApiClient(get_remote_api_settings())
    try:
        yield client
    finally:
        await client.close()


def get_local_seller_service(
        remote: Annotated[RemoteApiClient, Depends(get_remote_api_client)],
) -> LocalSellerService:
    return LocalSellerService(remote)


ParserServiceDep = Annotated[ParserService, Depends(get_parser_service)]
LocalSellerServiceDep = Annotated[
    LocalSellerService,
    Depends(get_local_seller_service),
]
