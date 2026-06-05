"""CRDT engine: owns the pycrdt Doc lifecycle for each table.

Every table is a single pycrdt Doc with two root-level Maps:
- "schema": column definitions serialized as JSON strings
- "rows":   row data keyed by UUID row IDs
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pycrdt import Doc, Map

from shelf.schema import ColumnDef, TableSchema, validate_row

# Doc helpers

def create_table_doc(schema: TableSchema) -> Doc:
    """Build a new pycrdt Doc for a table and populate its schema Map."""
    doc = Doc()
    schema_map = Map()
    rows_map = Map()
    doc["schema"] = schema_map
    doc["rows"] = rows_map

    # Store each column definition as a JSON string keyed by column name.
    # Also store an explicit column order list since Map iteration order
    # is not deterministic in pycrdt.
    with doc.transaction():
        schema_map["__table_name__"] = schema.table_name
        schema_map["__column_order__"] = json.dumps([c.name for c in schema.columns])
        for col in schema.columns:
            schema_map[col.name] = json.dumps(col.to_dict())

    return doc


def read_schema(doc: Doc) -> TableSchema:
    """Reconstruct a TableSchema from the CRDT Doc's schema Map.

    Column order is preserved using the ``__column_order__`` key that
    ``create_table_doc`` and ``add_column`` maintain.
    """
    schema_map: Map = doc["schema"]
    table_name = str(schema_map["__table_name__"])
    order: list[str] = json.loads(str(schema_map["__column_order__"]))
    columns = [
        ColumnDef.from_dict(json.loads(str(schema_map[name])))
        for name in order
    ]
    return TableSchema(table_name=table_name, columns=columns)


# Row operations

def insert_row(doc: Doc, data: dict[str, Any]) -> str:
    """Validate *data* against the table schema, then insert a new row.

    Returns the generated UUID row ID.
    """
    schema = read_schema(doc)
    validated = validate_row(schema, data)

    row_id = uuid.uuid4().hex
    rows_map: Map = doc["rows"]
    row_map = Map()

    with doc.transaction():
        rows_map[row_id] = row_map
        for col_name, value in validated.items():
            row_map[col_name] = _to_crdt_value(value)

    return row_id


def update_row(doc: Doc, row_id: str, data: dict[str, Any]) -> None:
    schema = read_schema(doc)
    validated = validate_row(schema, data, partial=True)

    rows_map: Map = doc["rows"]
    if row_id not in rows_map:
        raise KeyError(f"Row {row_id!r} not found")

    row_map: Map = rows_map[row_id]
    with doc.transaction():
        for col_name, value in validated.items():
            row_map[col_name] = _to_crdt_value(value)


def delete_row(doc: Doc, row_id: str) -> None:
    rows_map: Map = doc["rows"]
    if row_id not in rows_map:
        raise KeyError(f"Row {row_id!r} not found")
    with doc.transaction():
        del rows_map[row_id]


def get_row(doc: Doc, row_id: str) -> dict[str, Any]:
    rows_map: Map = doc["rows"]
    if row_id not in rows_map:
        raise KeyError(f"Row {row_id!r} not found")
    row_map: Map = rows_map[row_id]
    return {k: _from_crdt_value(v) for k, v in row_map.items()}


def list_rows(doc: Doc) -> list[tuple[str, dict[str, Any]]]:
    rows_map: Map = doc["rows"]
    result: list[tuple[str, dict[str, Any]]] = []
    for row_id in rows_map:
        row_map: Map = rows_map[row_id]
        row_dict = {k: _from_crdt_value(v) for k, v in row_map.items()}
        result.append((row_id, row_dict))
    return result


def row_count(doc: Doc) -> int:
    """Return the number of rows in the table."""
    rows_map: Map = doc["rows"]
    return len(rows_map)


# Column operations

def add_column(
    doc: Doc,
    column: ColumnDef,
    default: Any = None,
) -> None:
    """Add a new column to the table schema and backfill existing rows."""
    schema_map: Map = doc["schema"]
    if column.name in schema_map:
        raise ValueError(f"Column {column.name!r} already exists")

    rows_map: Map = doc["rows"]
    fill_value = _to_crdt_value(default)

    with doc.transaction():
        schema_map[column.name] = json.dumps(column.to_dict())
        # Append the new column to the explicit order list
        order: list[str] = json.loads(str(schema_map["__column_order__"]))
        order.append(column.name)
        schema_map["__column_order__"] = json.dumps(order)
        for row_id in rows_map:
            row_map: Map = rows_map[row_id]
            row_map[column.name] = fill_value


# Serialization / sync helpers

def serialize_doc(doc: Doc) -> bytes:
    return doc.get_update()


def load_doc(state: bytes) -> Doc:
    """Recreate a Doc from a previously serialized binary blob."""
    doc = Doc()
    doc["schema"] = Map()
    doc["rows"] = Map()
    doc.apply_update(state)
    return doc


def get_state_vector(doc: Doc) -> bytes:
    """Return the Doc's state vector (used to compute diffs)."""
    return doc.get_state()


def get_diff_update(doc: Doc, remote_state: bytes) -> bytes:
    """Compute the binary update that the remote peer is missing.

    *remote_state* is the state vector received from the remote peer.
    """
    return doc.get_update(remote_state)


def apply_update(doc: Doc, update: bytes) -> None:
    doc.apply_update(update)


# Internal helpers

def _to_crdt_value(value: Any) -> Any:
    """Convert a Python value into something safe to store in a pycrdt Map.

    pycrdt Maps accept str, int, float, bool, bytes, and nested shared types.
    We store None as the string "__null__" to avoid issues with missing keys.
    Complex types (dicts, lists) are stored as JSON strings.
    """
    if value is None:
        return "__null__"
    if isinstance(value, (str, int, float, bool)):
        return value
    # Fallback: serialize as JSON
    return json.dumps(value)


def _from_crdt_value(value: Any) -> Any:
    if value == "__null__":
        return None
    return value
