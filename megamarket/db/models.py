from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from megamarket.db.base import Base
from megamarket.domain import SellerStatus


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


class SellerJob(Base):
    __tablename__ = "seller_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        server_default="active",
        nullable=False,
        index=True,
    )
    added: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    stopped_reason: Mapped[str] = mapped_column(
        String(64),
        default="",
        server_default="",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class SellerJobItem(Base):
    __tablename__ = "seller_job_items"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("seller_jobs.job_id", ondelete="CASCADE"),
        primary_key=True,
    )
    seller_id: Mapped[str] = mapped_column(
        ForeignKey("sellers.seller_id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
