"""Add description to parts/orders/devices/bom, remove uom from parts

Revision ID: 007
Revises: 006
Create Date: 2026-03-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("parts", sa.Column("description", sa.Text(), nullable=True))
    op.drop_column("parts", "uom")

    op.add_column("orders", sa.Column("description", sa.Text(), nullable=True))

    op.add_column("devices", sa.Column("description", sa.Text(), nullable=True))

    op.add_column("device_bom_versions", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("device_bom_versions", "description")
    op.drop_column("devices", "description")
    op.drop_column("orders", "description")

    op.add_column("parts", sa.Column("uom", sa.String(16), nullable=False, server_default="шт"))
    op.drop_column("parts", "description")
