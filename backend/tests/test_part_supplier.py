from app.api.parts import _normalize_part_payload
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
