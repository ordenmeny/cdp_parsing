"""create sellers table

Revision ID: 20260903_01
Revises:
Create Date: 2026-09-03
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260903_01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


seller_status = sa.Enum(
    "confirmed",
    "unconfirmed",
    "incorrect",
    name="seller_status",
)


def upgrade() -> None:
    op.create_table(
        "sellers",
        sa.Column("seller_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("link_to_seller", sa.String(length=2048), nullable=False),
        sa.Column("link_to_card", sa.Text(), nullable=False),
        sa.Column(
            "status",
            seller_status,
            server_default="unconfirmed",
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("ogrn", sa.String(length=32), nullable=False),
        sa.Column("official_name", sa.String(length=1024), nullable=False),
        sa.Column("inn", sa.String(length=32), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("seller_id", name=op.f("pk_sellers")),
        sa.UniqueConstraint("link_to_seller", name=op.f("uq_sellers_link_to_seller")),
        sa.UniqueConstraint("name", name=op.f("uq_sellers_name")),
    )
    op.create_index(
        op.f("ix_sellers_status"),
        "sellers",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sellers_status"), table_name="sellers")
    op.drop_table("sellers")
    seller_status.drop(op.get_bind(), checkfirst=True)
