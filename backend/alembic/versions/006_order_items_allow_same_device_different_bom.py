"""Allow same device with different BOM in order items

Revision ID: 006
Revises: 005
Create Date: 2026-03-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_order_items_order_device", "order_items", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_order_items_order_device",
        "order_items",
        ["order_id", "device_id"],
    )
