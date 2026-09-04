"""create seller processing jobs

Revision ID: 20260904_03
Revises: 20260904_02
Create Date: 2026-09-04
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_03"
down_revision: str | Sequence[str] | None = "20260904_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seller_jobs",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("input_path", sa.Text(), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column("added", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "stopped_reason",
            sa.String(length=64),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id", name=op.f("pk_seller_jobs")),
    )
    op.create_index(op.f("ix_seller_jobs_status"), "seller_jobs", ["status"])
    op.create_index(
        op.f("ix_seller_jobs_expires_at"),
        "seller_jobs",
        ["expires_at"],
    )

    op.create_table(
        "seller_job_items",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("seller_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "processed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["seller_jobs.job_id"],
            name=op.f("fk_seller_job_items_job_id_seller_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["seller_id"],
            ["sellers.seller_id"],
            name=op.f("fk_seller_job_items_seller_id_sellers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "job_id",
            "seller_id",
            name=op.f("pk_seller_job_items"),
        ),
    )
    op.create_index(
        op.f("ix_seller_job_items_seller_id"),
        "seller_job_items",
        ["seller_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_seller_job_items_seller_id"),
        table_name="seller_job_items",
    )
    op.drop_table("seller_job_items")
    op.drop_index(op.f("ix_seller_jobs_expires_at"), table_name="seller_jobs")
    op.drop_index(op.f("ix_seller_jobs_status"), table_name="seller_jobs")
    op.drop_table("seller_jobs")
