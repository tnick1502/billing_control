from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def decimal_to_str(v: Any) -> str:
    if isinstance(v, Decimal):
        return str(v)
    return v


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    full_name: str | None = None
    role: str = "employee"
    is_active: bool = True


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=64)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserRead(BaseSchema):
    id: int
    username: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AuthToken(BaseModel):
    token: str
    user: UserRead


class AuditLogRead(BaseSchema):
    id: int
    user_id: int | None
    username: str | None
    role: str | None
    action: str
    method: str
    path: str
    status_code: int | None
    details: str | None
    created_at: datetime


class DeviceBase(BaseModel):
    primary_name: str
    model: str | None = None
    description: str | None = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    primary_name: str | None = None
    model: str | None = None
    description: str | None = None


class DeviceRead(DeviceBase):
    id: int
    is_archived: bool
    created_at: datetime


class DeviceArchiveUpdate(BaseModel):
    is_archived: bool


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
    cipher: str | None = None
    article: str | None = None
    part_type: str | None = None
    supplier: str | None = None
    description: str | None = None


class PartCreate(PartBase):
    pass


class PartUpdate(BaseModel):
    name: str | None = None
    cipher: str | None = None
    article: str | None = None
    part_type: str | None = None
    supplier: str | None = None
    description: str | None = None


class PartRead(PartBase):
    id: int
    is_archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class PartArchiveUpdate(BaseModel):
    is_archived: bool


class OrderBase(BaseModel):
    order_date: date
    customer: str | None = None
    contract_no: str | None = None
    description: str | None = None


class OrderCreate(OrderBase):
    pass


class OrderUpdate(BaseModel):
    order_date: date | None = None
    customer: str | None = None
    contract_no: str | None = None
    description: str | None = None


class OrderRead(OrderBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderItemCreate(BaseModel):
    device_id: int
    bom_version_id: int | None = None  # Default: active BOM for device
    qty: Decimal = Field(gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    note: str | None = None


class OrderItemUpdate(BaseModel):
    bom_version_id: int | None = None
    qty: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    note: str | None = None


class OrderPartItemCreate(BaseModel):
    part_id: int
    qty: Decimal = Field(gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    note: str | None = None


class OrderPartItemUpdate(BaseModel):
    qty: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, ge=0)
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
    part_id: int | None = None
    sub_device_id: int | None = None
    sub_bom_version_id: int | None = None
    qty_per_device: int = Field(ge=1)
    note: str | None = None

    @model_validator(mode="after")
    def check_exactly_one(self) -> "BomItemCreate":
        has_part = self.part_id is not None
        has_sub = self.sub_device_id is not None
        if has_part == has_sub:
            raise ValueError("Укажите либо деталь (part_id), либо подприбор (sub_device_id)")
        if self.sub_bom_version_id is not None and not has_sub:
            raise ValueError("sub_bom_version_id можно указать только вместе с sub_device_id")
        return self


class BomItemUpdate(BaseModel):
    qty_per_device: int | None = Field(None, ge=1)
    note: str | None = None


class BomItemRead(BaseModel):
    id: int
    bom_version_id: int
    part_id: int | None
    sub_device_id: int | None
    sub_bom_version_id: int | None
    qty_per_device: int
    note: str | None
    item_type: str

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
    qty_delivered: Decimal = Field(ge=0)


class MonthlyPlanPartUpdate(BaseModel):
    """Ручная корректировка строки плана: итоговая потребность и/или фактически поставлено."""

    qty_final: Decimal | None = Field(default=None, ge=0)
    qty_delivered: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def at_least_one(self) -> "MonthlyPlanPartUpdate":
        if self.qty_final is None and self.qty_delivered is None:
            raise ValueError("Укажите qty_final и/или qty_delivered")
        return self


class MonthlyPlanInvoiceLinkBatchItem(BaseModel):
    """Одна строка атомарной привязки счёта к деталям месячного плана."""

    plan_part_id: int = Field(gt=0)
    qty_covered: Decimal = Field(gt=0)
    note: str | None = None


class MonthlyPlanInvoiceLinkBatchCreate(BaseModel):
    """Один счёт и выбранные пользователем строки месячного плана."""

    invoice_id: int = Field(gt=0)
    items: list[MonthlyPlanInvoiceLinkBatchItem] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_plan_parts(self) -> "MonthlyPlanInvoiceLinkBatchCreate":
        ids = [item.plan_part_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Каждую деталь можно указать только один раз")
        return self


class InvoiceBase(BaseModel):
    invoice_no: str
    invoice_date: date
    supplier: str | None = None
    total_amount: Decimal | None = None
    payment_date: date | None = None
    description: str | None = None
    note: str | None = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    invoice_no: str | None = None
    invoice_date: date | None = None
    supplier: str | None = None
    total_amount: Decimal | None = None
    payment_date: date | None = None
    description: str | None = None
    note: str | None = None


class InvoiceRead(BaseModel):
    id: int
    invoice_no: str
    invoice_date: date
    supplier: str | None
    total_amount: Decimal | None
    payment_date: date | None
    description: str | None
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})


class FileRead(BaseModel):
    id: int
    filename: str
    content_type: str | None
    size_bytes: int | None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoicePartLinkCreate(BaseModel):
    plan_id: int
    part_id: int
    # Необязательно (пустое = не задано), но если указано — строго положительно
    # (ноль/отрицательное бессмысленны для покрытия и отклоняются).
    qty_covered: Decimal | None = Field(default=None, gt=0)
    note: str | None = None


class InvoicePartLinkUpdate(BaseModel):
    qty_covered: Decimal | None = Field(default=None, gt=0)
    note: str | None = None


class InvoicePartLinkRead(BaseModel):
    id: int
    invoice_id: int
    plan_id: int
    part_id: int
    qty_covered: Decimal | None
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, json_encoders={Decimal: decimal_to_str})
