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
    sku: str
    primary_name: str
    model: str | None = None
    is_active: bool = True


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    sku: str | None = None
    primary_name: str | None = None
    model: str | None = None
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
    sku: str
    name: str
    uom: str
    is_active: bool = True


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    sku: str | None = None
    name: str | None = None
    uom: str | None = None
    is_active: bool | None = None


class PartRead(PartBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class OrderBase(BaseModel):
    order_no: str
    status: str = "draft"
    order_date: date


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    order_no: str | None = None
    status: str | None = None
    order_date: date | None = None


class OrderRead(OrderBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderItemCreate(BaseModel):
    device_id: int
    qty: Decimal
    price: Decimal | None = None
    note: str | None = None


class OrderItemUpdate(BaseModel):
    qty: Decimal | None = None
    price: Decimal | None = None
    note: str | None = None


class OrderItemRead(BaseModel):
    id: int
    order_id: int
    device_id: int
    qty: Decimal
    price: Decimal | None
    note: str | None

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class BomVersionBase(BaseModel):
    version: int
    status: str = "draft"


class BomVersionCreate(BomVersionBase):
    pass


class BomVersionUpdate(BaseModel):
    status: str | None = None


class BomVersionRead(BaseModel):
    id: int
    device_id: int
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
    order_status: str | None = "confirmed"


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
    qty_buffered: Decimal | None
    qty_final: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class InvoiceBase(BaseModel):
    invoice_no: str
    invoice_date: date
    currency: str = "RUB"
    total_amount: Decimal | None = None
    status: str = "received"
    note: str | None = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    invoice_no: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    status: str | None = None
    note: str | None = None


class InvoiceRead(BaseModel):
    id: int
    invoice_no: str
    invoice_date: date
    currency: str
    total_amount: Decimal | None
    status: str
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
