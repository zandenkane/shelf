"""Tests for the CRDT engine."""

import pytest

from shelf.engine import (
    add_column,
    apply_update,
    create_table_doc,
    delete_row,
    get_diff_update,
    get_row,
    get_state_vector,
    insert_row,
    list_rows,
    load_doc,
    read_schema,
    row_count,
    serialize_doc,
    update_row,
)
from shelf.schema import ColumnDef, ColumnType, TableSchema


def _make_schema() -> TableSchema:
    return TableSchema(
        table_name="people",
        columns=[
            ColumnDef(name="name", col_type=ColumnType.TEXT),
            ColumnDef(name="age", col_type=ColumnType.INTEGER, nullable=True),
        ],
    )


class TestCreateAndReadSchema:
    def test_round_trip(self):
        schema = _make_schema()
        doc = create_table_doc(schema)
        recovered = read_schema(doc)
        assert recovered.table_name == "people"
        assert len(recovered.columns) == 2
        assert recovered.columns[0].name == "name"

    def test_column_types_preserved(self):
        schema = _make_schema()
        doc = create_table_doc(schema)
        recovered = read_schema(doc)
        assert recovered.columns[1].col_type == ColumnType.INTEGER


class TestRowOperations:
    def test_insert_and_get(self):
        doc = create_table_doc(_make_schema())
        row_id = insert_row(doc, {"name": "Alice", "age": 30})
        row = get_row(doc, row_id)
        assert row["name"] == "Alice"
        assert row["age"] == 30

    def test_insert_with_defaults(self):
        doc = create_table_doc(_make_schema())
        row_id = insert_row(doc, {"name": "Bob"})
        row = get_row(doc, row_id)
        assert row["name"] == "Bob"
        # age is nullable, should be None (stored as __null__)
        assert row["age"] is None

    def test_update_row(self):
        doc = create_table_doc(_make_schema())
        row_id = insert_row(doc, {"name": "Alice", "age": 30})
        update_row(doc, row_id, {"age": 31})
        row = get_row(doc, row_id)
        assert row["age"] == 31
        assert row["name"] == "Alice"

    def test_delete_row(self):
        doc = create_table_doc(_make_schema())
        row_id = insert_row(doc, {"name": "Alice", "age": 30})
        assert row_count(doc) == 1
        delete_row(doc, row_id)
        assert row_count(doc) == 0

    def test_list_rows(self):
        doc = create_table_doc(_make_schema())
        insert_row(doc, {"name": "Alice", "age": 30})
        insert_row(doc, {"name": "Bob", "age": 25})
        rows = list_rows(doc)
        assert len(rows) == 2
        names = {r[1]["name"] for r in rows}
        assert names == {"Alice", "Bob"}

    def test_get_missing_row_raises(self):
        doc = create_table_doc(_make_schema())
        with pytest.raises(KeyError):
            get_row(doc, "nonexistent")

    def test_update_missing_row_raises(self):
        doc = create_table_doc(_make_schema())
        with pytest.raises(KeyError):
            update_row(doc, "nonexistent", {"name": "X"})

    def test_delete_missing_row_raises(self):
        doc = create_table_doc(_make_schema())
        with pytest.raises(KeyError):
            delete_row(doc, "nonexistent")


class TestAddColumn:
    def test_add_column_updates_schema(self):
        doc = create_table_doc(_make_schema())
        new_col = ColumnDef(name="email", col_type=ColumnType.TEXT)
        add_column(doc, new_col)
        schema = read_schema(doc)
        assert any(c.name == "email" for c in schema.columns)

    def test_add_column_backfills_rows(self):
        doc = create_table_doc(_make_schema())
        insert_row(doc, {"name": "Alice", "age": 30})
        new_col = ColumnDef(name="email", col_type=ColumnType.TEXT)
        add_column(doc, new_col, default="unknown")
        rows = list_rows(doc)
        assert rows[0][1]["email"] == "unknown"

    def test_add_duplicate_column_raises(self):
        doc = create_table_doc(_make_schema())
        col = ColumnDef(name="name", col_type=ColumnType.TEXT)
        with pytest.raises(ValueError, match="already exists"):
            add_column(doc, col)


class TestSerialization:
    def test_serialize_and_load(self):
        doc = create_table_doc(_make_schema())
        insert_row(doc, {"name": "Alice", "age": 30})
        blob = serialize_doc(doc)
        doc2 = load_doc(blob)
        schema = read_schema(doc2)
        assert schema.table_name == "people"
        rows = list_rows(doc2)
        assert len(rows) == 1
        assert rows[0][1]["name"] == "Alice"


class TestRowCount:
    def test_empty_table(self):
        doc = create_table_doc(_make_schema())
        assert row_count(doc) == 0

    def test_after_inserts(self):
        doc = create_table_doc(_make_schema())
        insert_row(doc, {"name": "Alice", "age": 30})
        insert_row(doc, {"name": "Bob", "age": 25})
        assert row_count(doc) == 2

    def test_after_delete(self):
        doc = create_table_doc(_make_schema())
        rid = insert_row(doc, {"name": "Alice", "age": 30})
        insert_row(doc, {"name": "Bob", "age": 25})
        delete_row(doc, rid)
        assert row_count(doc) == 1


class TestColumnOrder:
    def test_column_order_preserved_after_add(self):
        doc = create_table_doc(_make_schema())
        new_col = ColumnDef(name="email", col_type=ColumnType.TEXT)
        add_column(doc, new_col)
        schema = read_schema(doc)
        names = [c.name for c in schema.columns]
        assert names == ["name", "age", "email"]


class TestInsertValidation:
    def test_unknown_column_rejected(self):
        doc = create_table_doc(_make_schema())
        with pytest.raises(ValueError, match="Unknown column"):
            insert_row(doc, {"name": "Alice", "bogus": "data"})

    def test_type_coercion_on_insert(self):
        doc = create_table_doc(_make_schema())
        row_id = insert_row(doc, {"name": "Alice", "age": "30"})
        row = get_row(doc, row_id)
        assert row["age"] == 30

    def test_update_with_coercion(self):
        doc = create_table_doc(_make_schema())
        row_id = insert_row(doc, {"name": "Alice", "age": 30})
        update_row(doc, row_id, {"age": "35"})
        row = get_row(doc, row_id)
        assert row["age"] == 35


class TestMerge:
    def test_two_docs_merge_via_updates(self):
        """Simulate two peers making independent edits and merging."""
        schema = _make_schema()

        # Peer A creates the table and inserts a row
        doc_a = create_table_doc(schema)
        insert_row(doc_a, {"name": "Alice", "age": 30})

        # Peer B starts from A's state, then both diverge
        state_a = serialize_doc(doc_a)
        doc_b = load_doc(state_a)

        # A adds another row
        insert_row(doc_a, {"name": "Charlie", "age": 40})

        # B adds a different row
        insert_row(doc_b, {"name": "Bob", "age": 25})

        # Exchange updates
        sv_a = get_state_vector(doc_a)
        sv_b = get_state_vector(doc_b)

        diff_for_a = get_diff_update(doc_b, sv_a)
        diff_for_b = get_diff_update(doc_a, sv_b)

        apply_update(doc_a, diff_for_a)
        apply_update(doc_b, diff_for_b)

        # Both docs should now have 3 rows
        rows_a = list_rows(doc_a)
        rows_b = list_rows(doc_b)
        assert len(rows_a) == 3
        assert len(rows_b) == 3

        names_a = {r[1]["name"] for r in rows_a}
        names_b = {r[1]["name"] for r in rows_b}
        assert names_a == {"Alice", "Bob", "Charlie"}
        assert names_a == names_b
