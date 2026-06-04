"""Tests for the Click CLI commands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from shelf.cli import cli


@pytest.fixture()
def runner(tmp_path: Path):
    """Return a CliRunner that points at a temp database."""
    db = str(tmp_path / "test.db")

    class BoundRunner:
        def __init__(self):
            self._runner = CliRunner()
            self._db = db

        def invoke(self, args: list[str], **kwargs):
            return self._runner.invoke(cli, ["--db", self._db] + args, **kwargs)

    return BoundRunner()


class TestTableCommands:
    def test_create_and_list(self, runner):
        result = runner.invoke(["table", "create", "tasks", "-c", "title:text"])
        assert result.exit_code == 0
        assert "created" in result.output.lower()

        result = runner.invoke(["table", "list"])
        assert result.exit_code == 0
        assert "tasks" in result.output

    def test_create_duplicate(self, runner):
        runner.invoke(["table", "create", "t", "-c", "a:text"])
        result = runner.invoke(["table", "create", "t", "-c", "b:text"])
        assert result.exit_code != 0

    def test_describe(self, runner):
        runner.invoke(["table", "create", "t", "-c", "name:text", "-c", "age:integer"])
        result = runner.invoke(["table", "describe", "t"])
        assert result.exit_code == 0
        assert "name" in result.output
        assert "age" in result.output

    def test_drop(self, runner):
        runner.invoke(["table", "create", "t", "-c", "a:text"])
        result = runner.invoke(["table", "drop", "t", "--yes"])
        assert result.exit_code == 0
        assert "dropped" in result.output.lower()

    def test_list_shows_row_count(self, runner):
        runner.invoke(["table", "create", "t", "-c", "name:text"])
        runner.invoke(["row", "add", "t", "-d", '{"name": "Alice"}'])
        result = runner.invoke(["table", "list"])
        assert result.exit_code == 0
        assert "1" in result.output

    def test_describe_missing(self, runner):
        result = runner.invoke(["table", "describe", "ghost"])
        assert result.exit_code != 0

    def test_drop_missing(self, runner):
        result = runner.invoke(["table", "drop", "ghost", "--yes"])
        assert result.exit_code != 0


class TestRowCommands:
    def test_add_and_list(self, runner):
        runner.invoke(["table", "create", "t", "-c", "name:text", "-c", "age:integer"])
        result = runner.invoke(["row", "add", "t", "-d", '{"name": "Alice", "age": 30}'])
        assert result.exit_code == 0
        assert "added" in result.output.lower()

        result = runner.invoke(["row", "list", "t"])
        assert result.exit_code == 0
        assert "Alice" in result.output

    def test_add_invalid_json(self, runner):
        runner.invoke(["table", "create", "t", "-c", "a:text"])
        result = runner.invoke(["row", "add", "t", "-d", "not json"])
        assert result.exit_code != 0

    def test_get_row(self, runner):
        runner.invoke(["table", "create", "t", "-c", "name:text"])
        result = runner.invoke(["row", "add", "t", "-d", '{"name": "Bob"}'])
        result = runner.invoke(["row", "list", "t"])
        assert "Bob" in result.output

    def test_delete_row_missing(self, runner):
        runner.invoke(["table", "create", "t", "-c", "a:text"])
        result = runner.invoke(["row", "delete", "t", "nonexistent"])
        assert result.exit_code != 0


class TestColumnCommands:
    def test_add_column(self, runner):
        runner.invoke(["table", "create", "t", "-c", "name:text"])
        result = runner.invoke(["column", "add", "t", "--name", "email", "--type", "text"])
        assert result.exit_code == 0
        assert "added" in result.output.lower()

        result = runner.invoke(["table", "describe", "t"])
        assert "email" in result.output


class TestExportImport:
    def test_export_json(self, runner, tmp_path: Path):
        runner.invoke(["table", "create", "t", "-c", "name:text"])
        runner.invoke(["row", "add", "t", "-d", '{"name": "Alice"}'])
        out = str(tmp_path / "export.json")
        result = runner.invoke(["export", "t", "-o", out])
        assert result.exit_code == 0

        data = json.loads(Path(out).read_text())
        assert data["table"] == "t"
        assert len(data["rows"]) == 1

    def test_import_json(self, runner, tmp_path: Path):
        runner.invoke(["table", "create", "t", "-c", "name:text"])
        export_file = tmp_path / "data.json"
        export_file.write_text(json.dumps({
            "rows": [{"name": "Bob"}, {"name": "Carol"}]
        }))
        result = runner.invoke(["import", "t", str(export_file)])
        assert result.exit_code == 0
        assert "2" in result.output

        result = runner.invoke(["row", "list", "t"])
        assert "Bob" in result.output
        assert "Carol" in result.output


class TestRowCount:
    def test_count_empty_table(self, runner):
        runner.invoke(["table", "create", "t", "-c", "a:text"])
        result = runner.invoke(["row", "count", "t"])
        assert result.exit_code == 0
        assert "0" in result.output

    def test_count_with_rows(self, runner):
        runner.invoke(["table", "create", "t", "-c", "name:text"])
        runner.invoke(["row", "add", "t", "-d", '{"name": "Alice"}'])
        runner.invoke(["row", "add", "t", "-d", '{"name": "Bob"}'])
        result = runner.invoke(["row", "count", "t"])
        assert result.exit_code == 0
        assert "2" in result.output

    def test_count_missing_table(self, runner):
        result = runner.invoke(["row", "count", "ghost"])
        assert result.exit_code != 0


class TestSyncCommands:
    def test_add_peer(self, runner):
        result = runner.invoke(["sync", "add-peer", "127.0.0.1:9876"])
        assert result.exit_code == 0
        assert "registered" in result.output.lower()

    def test_remove_peer(self, runner):
        runner.invoke(["sync", "add-peer", "127.0.0.1:9876"])
        result = runner.invoke(["sync", "remove-peer", "127.0.0.1:9876"])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()

    def test_remove_peer_bad_format(self, runner):
        result = runner.invoke(["sync", "remove-peer", "noport"])
        assert result.exit_code != 0

    def test_status(self, runner):
        runner.invoke(["sync", "add-peer", "10.0.0.1:8888"])
        result = runner.invoke(["sync", "status"])
        assert result.exit_code == 0
        assert "10.0.0.1" in result.output

    def test_status_empty(self, runner):
        result = runner.invoke(["sync", "status"])
        assert result.exit_code == 0
        assert "no peers" in result.output.lower()

    def test_sync_now_no_peers(self, runner):
        result = runner.invoke(["sync", "now"])
        assert result.exit_code == 0
        assert "no peers" in result.output.lower()
