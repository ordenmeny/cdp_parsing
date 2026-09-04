"""rename confirmed seller status to correct

Revision ID: 20260904_02
Revises: 20260903_01
Create Date: 2026-09-04
"""
from collections.abc import Sequence

from alembic import op


revision: str = "20260904_02"
down_revision: str | Sequence[str] | None = "20260903_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE seller_status RENAME VALUE 'confirmed' TO 'correct'")


def downgrade() -> None:
    op.execute("ALTER TYPE seller_status RENAME VALUE 'correct' TO 'confirmed'")
