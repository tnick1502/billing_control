from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Order, OrderItem
from app.schemas.common import (
    OrderCreate,
    OrderRead,
    OrderUpdate,
    OrderItemCreate,
    OrderItemRead,
    OrderItemUpdate,
)

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderRead])
async def list_orders(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Order).order_by(Order.order_date.desc()))
    return result.scalars().all()


@router.post("", response_model=OrderRead)
async def create_order(data: OrderCreate, session: AsyncSession = Depends(get_db)):
    order = Order(**data.model_dump())
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return order


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(order_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.patch("/{order_id}", response_model=OrderRead)
async def update_order(order_id: int, data: OrderUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(order, k, v)
    await session.flush()
    await session.refresh(order)
    return order


@router.delete("/{order_id}", status_code=204)
async def delete_order(order_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    await session.delete(order)
    return None


@router.get("/{order_id}/items", response_model=list[OrderItemRead])
async def list_order_items(order_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    return result.scalars().all()


@router.post("/{order_id}/items", response_model=OrderItemRead)
async def create_order_item(order_id: int, data: OrderItemCreate, session: AsyncSession = Depends(get_db)):
    item = OrderItem(order_id=order_id, **data.model_dump())
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return item


@router.patch("/{order_id}/items/{item_id}", response_model=OrderItemRead)
async def update_order_item(order_id: int, item_id: int, data: OrderItemUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(OrderItem).where(OrderItem.id == item_id, OrderItem.order_id == order_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Order item not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await session.flush()
    await session.refresh(item)
    return item


@router.delete("/{order_id}/items/{item_id}", status_code=204)
async def delete_order_item(order_id: int, item_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(OrderItem).where(OrderItem.id == item_id, OrderItem.order_id == order_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Order item not found")
    await session.delete(item)
    return None
