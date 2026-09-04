from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from megamarket.domain import SellerStatus


class SellerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seller_id: str
    name: str
    link_to_seller: str
    link_to_card: str
    status: SellerStatus
    email: str
    ogrn: str
    official_name: str
    inn: str
    phone: str
    rating: float | None


class SellerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    seller_id: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("seller_id", "id"),
    )
    name: str | None = Field(default=None, min_length=1)

    link_to_seller: str | None = Field(default=None, min_length=1)
    link_to_card: str | None = Field(default=None, min_length=1)
    status: SellerStatus | None = None
    email: str | None = None
    ogrn: str | None = None
    official_name: str | None = None
    inn: str | None = None
    phone: str | None = None
    rating: float | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "SellerUpdate":
        identifiers = (
            int(self.seller_id is not None)
            + int(self.name is not None)
        )
        if identifiers != 1:
            raise ValueError(
                "Укажите ровно один идентификатор: seller_id/id или name"
            )

        changed = self.model_fields_set - {"seller_id", "name"}
        if not changed:
            raise ValueError("Не указаны поля для изменения")

        required_values = {
            "link_to_seller",
            "link_to_card",
            "status",
            "email",
            "ogrn",
            "official_name",
            "inn",
            "phone",
        }
        null_values = {
            field
            for field in changed & required_values
            if getattr(self, field) is None
        }
        if null_values:
            raise ValueError(
                "Поля не могут быть null: " + ", ".join(sorted(null_values))
            )
        return self

    def changes(self) -> dict[str, object]:
        return self.model_dump(
            exclude_unset=True,
            exclude={"seller_id", "name"},
        )


class DefineSellersResponse(BaseModel):
    added: int
    selected: int
    processed: int
    confirmed: int
    incorrect: int
    unknown: int
    stopped_reason: str
