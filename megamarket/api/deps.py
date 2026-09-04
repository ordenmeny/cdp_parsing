from typing import Annotated

from fastapi import Depends

from megamarket.db.deps import AsyncSessionDep
from megamarket.repositories.sellers import SellerRepository
from megamarket.services.parser import ParserService
from megamarket.services.sellers import SellerService


def get_seller_service(session: AsyncSessionDep) -> SellerService:
    return SellerService(SellerRepository(session))


SellerServiceDep = Annotated[SellerService, Depends(get_seller_service)]


def get_parser_service() -> ParserService:
    return ParserService()


ParserServiceDep = Annotated[ParserService, Depends(get_parser_service)]
