from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from megamarket.domain import SellerInfo, SellerObservationState
from megamarket.schemas.sellers import DefineSellersResponse


class SellerCandidate(BaseModel):
    seller_id: str
    name: str
    link_to_seller: str


class SellerSelectionRequest(BaseModel):
    """Явный список продавцов для проверки."""

    model_config = ConfigDict(extra="forbid")

    seller_ids: list[str] = Field(min_length=1)

    @field_validator("seller_ids")
    @classmethod
    def normalize_seller_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            seller_id = value.strip()
            if not seller_id:
                raise ValueError("Идентификатор продавца не может быть пустым")
            if seller_id not in seen:
                normalized.append(seller_id)
                seen.add(seller_id)
        return normalized


class SellerJobStartResponse(BaseModel):
    job_id: str
    added: int
    filename: str | None
    sellers: list[SellerCandidate]


class SellerObservation(BaseModel):
    seller_id: str = Field(min_length=1)
    state: SellerObservationState
    info: SellerInfo | None = None

    @model_validator(mode="after")
    def validate_info(self) -> "SellerObservation":
        if self.state is SellerObservationState.FOUND and self.info is None:
            raise ValueError("Для найденного продавца нужны данные страницы")
        if self.state is not SellerObservationState.FOUND and self.info is not None:
            raise ValueError("Данные страницы допустимы только для состояния found")
        return self


class SellerObservationResponse(BaseModel):
    seller_id: str
    status: str
    outcome: str


class SellerJobFinishRequest(BaseModel):
    stopped_reason: str = Field(default="", max_length=64)


class SellerJobFinishResponse(DefineSellersResponse):
    job_id: str
    filename: str | None
    has_file: bool
