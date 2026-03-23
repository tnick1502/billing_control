"""Add BOM name, order_item bom_version_id

Revision ID: 004
Revises: 003
Create Date: 2025-03-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("device_bom_versions", sa.Column("name", sa.String(128), nullable=True))
    op.add_column(
        "order_items",
        sa.Column("bom_version_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_order_items_bom_version",
        "order_items",
        "device_bom_versions",
        ["bom_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Allow same device with different BOMs in monthly plan
    op.drop_constraint("uq_monthly_plan_devices_plan_device", "monthly_plan_devices", type_="unique")
    op.create_unique_constraint(
        "uq_monthly_plan_devices_plan_device_bom",
        "monthly_plan_devices",
        ["plan_id", "device_id", "bom_version_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_monthly_plan_devices_plan_device_bom", "monthly_plan_devices", type_="unique")
    op.create_unique_constraint("uq_monthly_plan_devices_plan_device", "monthly_plan_devices", ["plan_id", "device_id"])
    op.drop_constraint("fk_order_items_bom_version", "order_items", type_="foreignkey")
    op.drop_column("order_items", "bom_version_id")
    op.drop_column("device_bom_versions", "name")
