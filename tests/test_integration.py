"""Integration test proving shelf works as a database end-to-end.

Imports everything from the top-level ``shelf`` package to verify the
public API is properly exported.
"""

from shelf import (
    ColumnDef,
    ColumnType,
    TableSchema,
    create_table_doc,
    delete_row,
    get_row,
    insert_row,
    list_rows,
    row_count,
    update_row,
)


def test_full_crud_workflow():
    """Create a table, insert rows, query, update, delete -- the whole loop."""
    # 1. Create a table with "name" (text) and "quantity" (integer) columns
    schema = TableSchema(
        table_name="inventory",
        columns=[
            ColumnDef(name="name", col_type=ColumnType.TEXT),
            ColumnDef(name="quantity", col_type=ColumnType.INTEGER),
        ],
    )
    doc = create_table_doc(schema)

    # 2. Insert 3 items
    id_drill = insert_row(doc, {"name": "drill", "quantity": 10})
    insert_row(doc, {"name": "ladder", "quantity": 5})
    id_projector = insert_row(doc, {"name": "projector", "quantity": 2})

    # 3. Query and verify 3 rows returned
    rows = list_rows(doc)
    assert len(rows) == 3
    names = {r[1]["name"] for r in rows}
    assert names == {"drill", "ladder", "projector"}

    # 4. Update one item's quantity
    update_row(doc, id_drill, {"quantity": 20})

    # 5. Verify the update took effect
    updated = get_row(doc, id_drill)
    assert updated["quantity"] == 20
    assert updated["name"] == "drill"

    # 6. Delete one item
    delete_row(doc, id_projector)

    # 7. Verify 2 rows remain
    assert row_count(doc) == 2
    remaining = list_rows(doc)
    remaining_names = {r[1]["name"] for r in remaining}
    assert remaining_names == {"drill", "ladder"}
