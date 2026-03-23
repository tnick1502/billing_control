"""Remove sku from devices/parts, order_no from orders

Revision ID: 005
Revises: 004
Create Date: 2026-03-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("devices_sku_key", "devices", type_="unique")
    op.drop_column("devices", "sku")

    op.drop_constraint("parts_sku_key", "parts", type_="unique")
    op.drop_column("parts", "sku")

    op.drop_constraint("orders_order_no_key", "orders", type_="unique")
    op.drop_column("orders", "order_no")


def downgrade() -> None:
    op.add_column("orders", sa.Column("order_no", sa.String(64), nullable=False, server_default="1"))
    op.create_unique_constraint("orders_order_no_key", "orders", ["order_no"])
    op.alter_column("orders", "order_no", server_default=None)

    op.add_column("parts", sa.Column("sku", sa.String(64), nullable=False, server_default="P-000"))
    op.create_unique_constraint("parts_sku_key", "parts", ["sku"])
    op.alter_column("parts", "sku", server_default=None)

    op.add_column("devices", sa.Column("sku", sa.String(64), nullable=False, server_default="DEV-001"))
    op.create_unique_constraint("devices_sku_key", "devices", ["sku"])
    op.alter_column("devices", "sku", server_default=None)
