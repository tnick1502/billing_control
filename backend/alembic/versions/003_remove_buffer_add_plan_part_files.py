"""Remove buffer, add plan part files

Revision ID: 003
Revises: 002
Create Date: 2025-03-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("monthly_plan_parts", "qty_buffered")
    op.create_table(
        "monthly_plan_part_files",
        sa.Column("plan_part_id", sa.BigInteger(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_part_id"], ["monthly_plan_parts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_part_id", "file_id"),
    )


def downgrade() -> None:
    op.drop_table("monthly_plan_part_files")
    op.add_column("monthly_plan_parts", sa.Column("qty_buffered", sa.Numeric(18, 6), nullable=True))
