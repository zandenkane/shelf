"""shelf: CRDT-powered collaborative database for the terminal."""

__version__ = "0.1.0"

from shelf.engine import (
    create_table_doc,
    delete_row,
    get_row,
    insert_row,
    list_rows,
    row_count,
    update_row,
)
from shelf.schema import (
    ColumnDef,
    ColumnType,
    TableSchema,
    coerce_value,
    parse_column_spec,
    validate_row,
)

__all__ = [
    "__version__",
    "ColumnDef",
    "ColumnType",
    "TableSchema",
    "coerce_value",
    "parse_column_spec",
    "validate_row",
    "create_table_doc",
    "delete_row",
    "get_row",
    "insert_row",
    "list_rows",
    "row_count",
    "update_row",
]
