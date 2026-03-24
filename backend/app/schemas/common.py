from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


def decimal_to_str(v: Any) -> str:
    if isinstance(v, Decimal):
        return str(v)
    return v


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class DeviceBase(BaseModel):
    primary_name: str
    model: str | None = None
    description: str | None = None
    is_active: bool = True


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    primary_name: str | None = None
    model: str | None = None
    description: str | None = None
    is_active: bool | None = None


class DeviceRead(DeviceBase):
    id: int
    created_at: datetime


class DeviceAliasCreate(BaseModel):
    alias_name: str


class DeviceAliasRead(BaseModel):
    id: int
    device_id: int
    alias_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PartBase(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class PartRead(PartBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class OrderBase(BaseModel):
    status: str = "draft"
    order_date: date
    description: str | None = None


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    status: str | None = None
    order_date: date | None = None
    description: str | None = None


class OrderRead(OrderBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderItemCreate(BaseModel):
    device_id: int
    bom_version_id: int | None = None  # Default: active BOM for device
    qty: Decimal
    price: Decimal | None = None
    note: str | None = None


class OrderItemUpdate(BaseModel):
    bom_version_id: int | None = None
    qty: Decimal | None = None
    price: Decimal | None = None
    note: str | None = None


class OrderPartItemCreate(BaseModel):
    part_id: int
    qty: Decimal
    price: Decimal | None = None
    note: str | None = None


class OrderPartItemUpdate(BaseModel):
    qty: Decimal | None = None
    price: Decimal | None = None
    note: str | None = None


class OrderPartItemRead(BaseModel):
    id: int
    order_id: int
    part_id: int
    qty: Decimal
    price: Decimal | None
    note: str | None

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class BomVersionBrief(BaseModel):
    id: int
    name: str | None
    version: int

    model_config = ConfigDict(from_attributes=True)


class OrderItemRead(BaseModel):
    id: int
    order_id: int
    device_id: int
    bom_version_id: int | None
    bom_version: BomVersionBrief | None = None
    qty: Decimal
    price: Decimal | None
    note: str | None

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class BomVersionBase(BaseModel):
    name: str | None = None
    description: str | None = None
    version: int
    status: str = "draft"


class BomVersionCreate(BomVersionBase):
    pass


class BomVersionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class BomVersionRead(BaseModel):
    id: int
    device_id: int
    name: str | None
    description: str | None = None
    version: int
    status: str
    valid_from: datetime
    valid_to: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BomItemCreate(BaseModel):
    part_id: int
    qty_per_device: Decimal
    scrap_rate: Decimal | None = None
    note: str | None = None


class BomItemUpdate(BaseModel):
    qty_per_device: Decimal | None = None
    scrap_rate: Decimal | None = None
    note: str | None = None


class BomItemRead(BaseModel):
    id: int
    bom_version_id: int
    part_id: int
    qty_per_device: Decimal
    scrap_rate: Decimal | None
    note: str | None

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class MonthlyPlanBase(BaseModel):
    month: date
    revision: int = 1
    status: str = "draft"
    note: str | None = None


class MonthlyPlanCreate(MonthlyPlanBase):
    pass


class MonthlyPlanUpdate(BaseModel):
    status: str | None = None
    note: str | None = None


class MonthlyPlanRead(BaseModel):
    id: int
    month: date
    revision: int
    status: str
    generated_at: datetime
    generated_by: str | None
    note: str | None

    model_config = ConfigDict(from_attributes=True)


class MonthlyPlanGenerate(BaseModel):
    month: date
    order_status: str | None = None  # None = все заказы (draft, confirmed и т.д.)
    replace: bool = True  # Удалить существующий план за месяц и создать новый


class MonthlyPlanDeviceRead(BaseModel):
    id: int
    plan_id: int
    device_id: int
    qty_total: Decimal
    bom_version_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class MonthlyPlanPartRead(BaseModel):
    id: int
    plan_id: int
    part_id: int
    qty_required: Decimal
    qty_final: Decimal
    qty_delivered: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class MonthlyPlanPartQtyDeliveredUpdate(BaseModel):
    qty_delivered: Decimal


class InvoiceBase(BaseModel):
    invoice_no: str | None = None  # Игнорируется при создании — подставляется str(id)
    invoice_date: date
    currency: str = "RUB"
    total_amount: Decimal | None = None
    status: str = "received"
    description: str | None = None
    note: str | None = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    invoice_date: date | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    status: str | None = None
    description: str | None = None
    note: str | None = None


class InvoiceRead(BaseModel):
    id: int
    invoice_no: str
    invoice_date: date
    currency: str
    total_amount: Decimal | None
    status: str
    description: str | None
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class FileRead(BaseModel):
    id: int
    storage: str
    bucket: str
    object_key: str
    content_type: str | None
    size_bytes: int | None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoicePartLinkCreate(BaseModel):
    plan_id: int
    part_id: int
    qty_covered: Decimal | None = None
    amount_allocated: Decimal | None = None
    note: str | None = None


class InvoicePartLinkUpdate(BaseModel):
    qty_covered: Decimal | None = None
    amount_allocated: Decimal | None = None
    note: str | None = None


class InvoicePartLinkRead(BaseModel):
    id: int
    invoice_id: int
    plan_id: int
    part_id: int
    qty_covered: Decimal | None
    amount_allocated: Decimal | None
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})
