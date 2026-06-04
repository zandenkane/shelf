"""Tests for the display rendering module."""

from io import StringIO

from rich.console import Console

from shelf.display import (
    _format_cell,
    render_error,
    render_message,
    render_row_detail,
    render_schema,
    render_table,
    render_tables,
)
from shelf.schema import ColumnDef, ColumnType, TableSchema


def _capture(fn, *args, **kwargs) -> str:
    """Run a display function and capture its terminal output."""
    import shelf.display as mod

    buf = StringIO()
    original = mod.console
    mod.console = Console(file=buf, force_terminal=True, width=120)
    try:
        fn(*args, **kwargs)
    finally:
        mod.console = original
    return buf.getvalue()


class TestFormatCell:
    def test_none_shows_null(self):
        result = _format_cell(None)
        assert "null" in result

    def test_string_passthrough(self):
        assert _format_cell("hello") == "hello"

    def test_int_to_str(self):
        assert _format_cell(42) == "42"

    def test_bool_to_str(self):
        assert _format_cell(True) == "True"


class TestRenderMessage:
    def test_message_appears_in_output(self):
        text = _capture(render_message, "All good")
        assert "All good" in text

    def test_error_appears_in_output(self):
        text = _capture(render_error, "Something broke")
        assert "Something broke" in text
        assert "Error" in text


class TestRenderTable:
    def test_rows_rendered(self):
        schema = TableSchema(
            table_name="test",
            columns=[ColumnDef(name="name", col_type=ColumnType.TEXT)],
        )
        rows = [("abc123def456", {"name": "Alice"})]
        text = _capture(render_table, schema, rows)
        assert "Alice" in text
        assert "abc123def456"[:12] in text

    def test_table_name_in_title(self):
        schema = TableSchema(
            table_name="people",
            columns=[ColumnDef(name="x", col_type=ColumnType.TEXT)],
        )
        text = _capture(render_table, schema, [])
        assert "people" in text


class TestRenderSchema:
    def test_columns_displayed(self):
        schema = TableSchema(
            table_name="items",
            columns=[
                ColumnDef(name="title", col_type=ColumnType.TEXT),
                ColumnDef(name="price", col_type=ColumnType.FLOAT),
            ],
        )
        text = _capture(render_schema, schema)
        assert "title" in text
        assert "price" in text
        assert "text" in text
        assert "float" in text


class TestRenderTables:
    def test_table_list_with_rows(self):
        from datetime import datetime

        tables = [
            {"name": "tasks", "id": "abcdef123456", "created_at": datetime(2026, 1, 1), "rows": 5},
        ]
        text = _capture(render_tables, tables)
        assert "tasks" in text
        assert "5" in text


class TestRenderRowDetail:
    def test_row_detail_shows_fields(self):
        text = _capture(
            render_row_detail,
            "abc123def456",
            {"name": "Alice", "age": 30},
        )
        assert "Alice" in text
        assert "30" in text
        assert "abc123def456" in text
