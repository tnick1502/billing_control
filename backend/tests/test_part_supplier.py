import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.parts import _normalize_part_payload, list_part_suppliers
from app.database import Base
from app.models.part import Part
from app.schemas.common import PartCreate, PartUpdate


def test_supplier_column_is_nullable_text():
    column = Part.__table__.c.supplier

    assert column.nullable is True
    assert column.type.length == 255


def test_supplier_is_available_in_create_and_update_contracts():
    created = PartCreate(name="Резистор", supplier="Поставщик")
    updated = PartUpdate(supplier=None)

    assert created.supplier == "Поставщик"
    assert "supplier" in updated.model_fields_set
    assert updated.supplier is None


def test_supplier_whitespace_is_normalized_to_null():
    payload = _normalize_part_payload({"name": "Резистор", "supplier": "   "})

    assert payload["supplier"] is None


def test_supplier_suggestions_are_unique_case_insensitive_and_include_archived_parts():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as session:
                session.add_all(
                    [
                        Part(name="A", supplier="ООО Альфа"),
                        Part(name="B", supplier="ооо альфа"),
                        Part(name="C", supplier=" Бета "),
                        Part(name="D", supplier="Архивный", is_archived=True),
                        Part(name="E", supplier=None),
                    ]
                )
                await session.flush()

                suppliers = await list_part_suppliers(session)

                assert len(suppliers) == 3
                assert {value.casefold() for value in suppliers} == {
                    "ооо альфа",
                    "бета",
                    "архивный",
                }
        finally:
            await engine.dispose()

    asyncio.run(run())
