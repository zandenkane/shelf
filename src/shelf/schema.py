"""Schema definitions and row validation powered by Pydantic."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, field_validator


class ColumnType(str, Enum):
    """Supported column data types."""

    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    JSON = "json"


class ColumnDef(BaseModel):

    name: str
    col_type: ColumnType
    nullable: bool = True
    default: Any = None

    @field_validator("name")
    @classmethod
    def name_must_be_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Column name must not be empty")
        return v

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "col_type": self.col_type.value,
            "nullable": self.nullable,
            "default": self.default,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ColumnDef:
        return cls(
            name=d["name"],
            col_type=ColumnType(d["col_type"]),
            nullable=d.get("nullable", True),
            default=d.get("default"),
        )


class TableSchema(BaseModel):
    """Full schema for a table: name plus ordered column list."""

    table_name: str
    columns: list[ColumnDef]

    @field_validator("table_name")
    @classmethod
    def name_must_be_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Table name must not be empty")
        return v

    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def get_column(self, name: str) -> ColumnDef | None:
        for c in self.columns:
            if c.name == name:
                return c
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "columns": [c.to_dict() for c in self.columns],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TableSchema:
        return cls(
            table_name=d["table_name"],
            columns=[ColumnDef.from_dict(c) for c in d["columns"]],
        )


def coerce_value(value: Any, col_type: ColumnType) -> Any:
    """Convert a raw value to the correct Python type for a column.

    Strings from CLI input are coerced to the target type. Values that are
    already the right type pass through unchanged.
    if value is None:
        return None

    if col_type == ColumnType.TEXT:
        return str(value)

    if col_type == ColumnType.INTEGER:
        return int(value)

    if col_type == ColumnType.FLOAT:
        return float(value)

    if col_type == ColumnType.BOOLEAN:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.lower()
            if low in ("true", "1", "yes"):
                return True
            if low in ("false", "0", "no"):
                return False
            raise ValueError(f"Cannot convert {value!r} to boolean")
        return bool(value)

    if col_type == ColumnType.DATETIME:
        if isinstance(value, datetime):
            return value.isoformat()
        # Validate it parses, then store as ISO string
        datetime.fromisoformat(str(value))
        return str(value)

    if col_type == ColumnType.JSON:
        if isinstance(value, str):
            # Validate it is valid JSON, then store the string
            json.loads(value)
            return value
        return json.dumps(value)

    raise ValueError(f"Unknown column type: {col_type}")


def validate_row(
    schema: TableSchema,
    data: dict[str, Any],
    *,
    partial: bool = False,
) -> dict[str, Any]:
    """Validate and coerce a dict of values against a table schema.

    When *partial* is True (used for updates), missing columns are allowed.
    validated: dict[str, Any] = {}
    known_names = {c.name for c in schema.columns}

    # Reject unknown columns
    for key in data:
        if key not in known_names:
            raise ValueError(f"Unknown column: {key!r}")

    for col in schema.columns:
        if col.name in data:
            raw = data[col.name]
            if raw is None:
                if not col.nullable:
                    raise ValueError(
                        f"Column {col.name!r} does not accept null values"
                    )
                validated[col.name] = None
            else:
                validated[col.name] = coerce_value(raw, col.col_type)
        elif not partial:
            # Full insert: use default or check nullable
            if col.default is not None:
                validated[col.name] = coerce_value(col.default, col.col_type)
            elif col.nullable:
                validated[col.name] = None
            else:
                raise ValueError(
                    f"Column {col.name!r} is required (not nullable, no default)"
                )

    return validated


def parse_column_spec(spec: str) -> ColumnDef:
    """Parse a CLI column specification like ``name:text`` or ``age:integer``.

    Returns a ColumnDef with nullable=True and no default.
    """
    parts = spec.split(":", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid column spec {spec!r}. Expected format: name:type"
        )
    name, type_str = parts
    try:
        col_type = ColumnType(type_str.lower())
    except ValueError:
        valid = ", ".join(t.value for t in ColumnType)
        raise ValueError(
            f"Unknown column type {type_str!r}. Valid types: {valid}"
        )
    return ColumnDef(name=name.strip(), col_type=col_type)
