"""Tests for schema validation and coercion."""

import pytest

from shelf.schema import (
    ColumnDef,
    ColumnType,
    TableSchema,
    coerce_value,
    parse_column_spec,
    validate_row,
)


class TestCoercion:
    def test_text(self):
        assert coerce_value(42, ColumnType.TEXT) == "42"

    def test_integer(self):
        assert coerce_value("42", ColumnType.INTEGER) == 42

    def test_float(self):
        assert coerce_value("3.14", ColumnType.FLOAT) == 3.14

    def test_boolean_true_strings(self):
        for v in ("true", "1", "yes", "True", "YES"):
            assert coerce_value(v, ColumnType.BOOLEAN) is True

    def test_boolean_false_strings(self):
        for v in ("false", "0", "no", "False", "NO"):
            assert coerce_value(v, ColumnType.BOOLEAN) is False

    def test_boolean_invalid(self):
        with pytest.raises(ValueError):
            coerce_value("maybe", ColumnType.BOOLEAN)

    def test_datetime(self):
        result = coerce_value("2024-01-15T10:30:00", ColumnType.DATETIME)
        assert result == "2024-01-15T10:30:00"

    def test_datetime_invalid(self):
        with pytest.raises(ValueError):
            coerce_value("not-a-date", ColumnType.DATETIME)

    def test_json_string(self):
        result = coerce_value('{"a": 1}', ColumnType.JSON)
        assert result == '{"a": 1}'

    def test_json_dict(self):
        result = coerce_value({"a": 1}, ColumnType.JSON)
        assert '"a"' in result

    def test_json_invalid(self):
        with pytest.raises(Exception):
            coerce_value("{bad json", ColumnType.JSON)

    def test_none_passthrough(self):
        assert coerce_value(None, ColumnType.TEXT) is None


class TestValidateRow:
    @pytest.fixture()
    def schema(self) -> TableSchema:
        return TableSchema(
            table_name="t",
            columns=[
                ColumnDef(name="name", col_type=ColumnType.TEXT, nullable=False),
                ColumnDef(name="score", col_type=ColumnType.FLOAT, nullable=True),
            ],
        )

    def test_valid_full_row(self, schema: TableSchema):
        result = validate_row(schema, {"name": "Alice", "score": "9.5"})
        assert result["name"] == "Alice"
        assert result["score"] == 9.5

    def test_missing_nullable_gets_none(self, schema: TableSchema):
        result = validate_row(schema, {"name": "Bob"})
        assert result["score"] is None

    def test_missing_required_raises(self, schema: TableSchema):
        with pytest.raises(ValueError, match="required"):
            validate_row(schema, {"score": 1.0})

    def test_unknown_column_raises(self, schema: TableSchema):
        with pytest.raises(ValueError, match="Unknown column"):
            validate_row(schema, {"name": "X", "bogus": "y"})

    def test_null_on_non_nullable_raises(self, schema: TableSchema):
        with pytest.raises(ValueError, match="null"):
            validate_row(schema, {"name": None, "score": 1.0})

    def test_partial_update(self, schema: TableSchema):
        result = validate_row(schema, {"score": 8.0}, partial=True)
        assert "name" not in result
        assert result["score"] == 8.0


class TestParseColumnSpec:
    def test_valid_spec(self):
        col = parse_column_spec("age:integer")
        assert col.name == "age"
        assert col.col_type == ColumnType.INTEGER

    def test_text_type(self):
        col = parse_column_spec("name:text")
        assert col.col_type == ColumnType.TEXT

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid column spec"):
            parse_column_spec("nocolon")

    def test_invalid_type(self):
        with pytest.raises(ValueError, match="Unknown column type"):
            parse_column_spec("x:bigint")


class TestColumnDef:
    def test_empty_name_rejected(self):
        with pytest.raises(ValueError):
            ColumnDef(name="  ", col_type=ColumnType.TEXT)

    def test_to_from_dict(self):
        col = ColumnDef(name="x", col_type=ColumnType.INTEGER, nullable=False, default=0)
        d = col.to_dict()
        restored = ColumnDef.from_dict(d)
        assert restored.name == "x"
        assert restored.col_type == ColumnType.INTEGER
        assert restored.nullable is False
        assert restored.default == 0


class TestTableSchema:
    def test_column_names(self):
        s = TableSchema(
            table_name="t",
            columns=[
                ColumnDef(name="a", col_type=ColumnType.TEXT),
                ColumnDef(name="b", col_type=ColumnType.INTEGER),
            ],
        )
        assert s.column_names() == ["a", "b"]

    def test_get_column(self):
        s = TableSchema(
            table_name="t",
            columns=[ColumnDef(name="a", col_type=ColumnType.TEXT)],
        )
        assert s.get_column("a") is not None
        assert s.get_column("z") is None

    def test_to_from_dict(self):
        s = TableSchema(
            table_name="t",
            columns=[ColumnDef(name="a", col_type=ColumnType.TEXT)],
        )
        d = s.to_dict()
        restored = TableSchema.from_dict(d)
        assert restored.table_name == "t"
        assert len(restored.columns) == 1
