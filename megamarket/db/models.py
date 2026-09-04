from enum import StrEnum

from sqlalchemy import Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from megamarket.db.base import Base


class SellerStatus(StrEnum):
    CORRECT = "correct"
    UNCONFIRMED = "unconfirmed"
    INCORRECT = "incorrect"


seller_status_enum = Enum(
    SellerStatus,
    name="seller_status",
    values_callable=lambda enum: [status.value for status in enum],
    validate_strings=True,
)


class Sellers(Base):
    __tablename__ = "sellers"

    seller_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    link_to_seller: Mapped[str] = mapped_column(
        String(2048),
        unique=True,
        nullable=False,
    )
    link_to_card: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SellerStatus] = mapped_column(
        seller_status_enum,
        default=SellerStatus.UNCONFIRMED,
        server_default=SellerStatus.UNCONFIRMED.value,
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    ogrn: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    official_name: Mapped[str] = mapped_column(
        String(1024),
        default="",
        nullable=False,
    )
    inn: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
