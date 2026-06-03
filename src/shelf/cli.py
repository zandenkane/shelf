"""Click CLI for shelf."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import click

from shelf import __version__, display, engine
from shelf.schema import ColumnDef, ColumnType, TableSchema, parse_column_spec
from shelf.storage import Storage

# Context management

class Ctx:

    def __init__(self, db_path: str | None = None) -> None:
        self.storage = Storage(db_path=db_path)


pass_ctx = click.make_pass_decorator(Ctx)


@click.group()
@click.option(
    "--db",
    default=None,
    envvar="SHELF_DB",
    help="Path to the SQLite database file.",
)
@click.version_option(version=__version__, prog_name="shelf")
@click.pass_context
def cli(ctx: click.Context, db: str | None) -> None:
    """shelf: CRDT-powered collaborative database for the terminal."""
    ctx.ensure_object(dict)
    ctx.obj = Ctx(db_path=db)


# table commands

@cli.group()
def table() -> None:
    """Create, list, describe, or drop tables."""


@table.command("create")
@click.argument("name")
@click.option(
    "-c",
    "--column",
    multiple=True,
    required=True,
    help='Column spec in "name:type" format (e.g. age:integer).',
)
@click.pass_context
def table_create(ctx: click.Context, name: str, column: tuple[str, ...]) -> None:
    app: Ctx = ctx.obj
    if app.storage.table_exists(name):
        display.render_error(f"Table {name!r} already exists.")
        raise SystemExit(1)

    columns = [parse_column_spec(spec) for spec in column]
    schema = TableSchema(table_name=name, columns=columns)
    doc = engine.create_table_doc(schema)
    state = engine.serialize_doc(doc)

    table_id = uuid.uuid4().hex
    app.storage.save_table(table_id, name, state)
    display.render_message(f"Table {name!r} created.")


@table.command("list")
@click.pass_context
def table_list(ctx: click.Context) -> None:
    """List all tables with row counts."""
    app: Ctx = ctx.obj
    tables = app.storage.list_tables()
    if not tables:
        display.render_message("No tables found.", style="yellow")
        return

    entries: list[dict] = []
    for t in tables:
        rows = 0
        try:
            _, state = app.storage.load_table_state(t.name)
            doc = engine.load_doc(state)
            rows = engine.row_count(doc)
        except Exception:
            pass
        entries.append({
            "name": t.name,
            "id": t.id,
            "created_at": t.created_at,
            "rows": rows,
        })
    display.render_tables(entries)


@table.command("describe")
@click.argument("name")
@click.pass_context
def table_describe(ctx: click.Context, name: str) -> None:
    app: Ctx = ctx.obj
    try:
        _, state = app.storage.load_table_state(name)
    except KeyError:
        display.render_error(f"Table {name!r} not found.")
        raise SystemExit(1)
    doc = engine.load_doc(state)
    schema = engine.read_schema(doc)
    display.render_schema(schema)


@table.command("drop")
@click.argument("name")
@click.confirmation_option(prompt="Are you sure you want to drop this table?")
@click.pass_context
def table_drop(ctx: click.Context, name: str) -> None:
    """Delete a table and all its data."""
    app: Ctx = ctx.obj
    try:
        app.storage.drop_table(name)
    except KeyError:
        display.render_error(f"Table {name!r} not found.")
        raise SystemExit(1)
    display.render_message(f"Table {name!r} dropped.")


# row commands

@cli.group()
def row() -> None:
    """Add, list, get, update, or delete rows."""


@row.command("add")
@click.argument("table_name")
@click.option(
    "-d",
    "--data",
    required=True,
    help="Row data as a JSON object.",
)
@click.pass_context
def row_add(ctx: click.Context, table_name: str, data: str) -> None:
    """Insert a new row into a table."""
    app: Ctx = ctx.obj
    try:
        table_id, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    try:
        row_data = json.loads(data)
    except json.JSONDecodeError as e:
        display.render_error(f"Invalid JSON: {e}")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    try:
        row_id = engine.insert_row(doc, row_data)
    except (ValueError, TypeError) as e:
        display.render_error(str(e))
        raise SystemExit(1)

    new_state = engine.serialize_doc(doc)
    app.storage.save_table(table_id, table_name, new_state)
    display.render_message(f"Row {row_id[:12]} added.")


@row.command("list")
@click.argument("table_name")
@click.pass_context
def row_list(ctx: click.Context, table_name: str) -> None:
    """List all rows in a table."""
    app: Ctx = ctx.obj
    try:
        _, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    schema = engine.read_schema(doc)
    rows = engine.list_rows(doc)
    if not rows:
        display.render_message("No rows.", style="yellow")
        return
    display.render_table(schema, rows)


@row.command("count")
@click.argument("table_name")
@click.pass_context
def row_count_cmd(ctx: click.Context, table_name: str) -> None:
    """Print the number of rows in a table."""
    app: Ctx = ctx.obj
    try:
        _, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    count = engine.row_count(doc)
    display.render_message(f"{count} row(s) in {table_name!r}.")


@row.command("get")
@click.argument("table_name")
@click.argument("row_id")
@click.pass_context
def row_get(ctx: click.Context, table_name: str, row_id: str) -> None:
    """Show a single row by ID."""
    app: Ctx = ctx.obj
    try:
        _, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    try:
        row_data = engine.get_row(doc, row_id)
    except KeyError:
        display.render_error(f"Row {row_id!r} not found.")
        raise SystemExit(1)
    display.render_row_detail(row_id, row_data)


@row.command("update")
@click.argument("table_name")
@click.argument("row_id")
@click.option("-d", "--data", required=True, help="Fields to update as JSON.")
@click.pass_context
def row_update(
    ctx: click.Context,
    table_name: str,
    row_id: str,
    data: str,
) -> None:
    app: Ctx = ctx.obj
    try:
        table_id, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    try:
        update_data = json.loads(data)
    except json.JSONDecodeError as e:
        display.render_error(f"Invalid JSON: {e}")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    try:
        engine.update_row(doc, row_id, update_data)
    except (KeyError, ValueError) as e:
        display.render_error(str(e))
        raise SystemExit(1)

    new_state = engine.serialize_doc(doc)
    app.storage.save_table(table_id, table_name, new_state)
    display.render_message(f"Row {row_id[:12]} updated.")


@row.command("delete")
@click.argument("table_name")
@click.argument("row_id")
@click.pass_context
def row_delete(ctx: click.Context, table_name: str, row_id: str) -> None:
    """Delete a row by ID."""
    app: Ctx = ctx.obj
    try:
        table_id, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    try:
        engine.delete_row(doc, row_id)
    except KeyError:
        display.render_error(f"Row {row_id!r} not found.")
        raise SystemExit(1)

    new_state = engine.serialize_doc(doc)
    app.storage.save_table(table_id, table_name, new_state)
    display.render_message(f"Row {row_id[:12]} deleted.")


# column commands

@cli.group()
def column() -> None:
    """Add columns to a table."""


@column.command("add")
@click.argument("table_name")
@click.option("--name", "col_name", required=True, help="Column name.")
@click.option(
    "--type",
    "col_type",
    required=True,
    type=click.Choice([t.value for t in ColumnType], case_sensitive=False),
    help="Column type.",
)
@click.option("--default", "default_val", default=None, help="Default value.")
@click.pass_context
def column_add(
    ctx: click.Context,
    table_name: str,
    col_name: str,
    col_type: str,
    default_val: str | None,
) -> None:
    """Add a new column to an existing table."""
    app: Ctx = ctx.obj
    try:
        table_id, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    col = ColumnDef(name=col_name, col_type=ColumnType(col_type))
    try:
        engine.add_column(doc, col, default=default_val)
    except ValueError as e:
        display.render_error(str(e))
        raise SystemExit(1)

    new_state = engine.serialize_doc(doc)
    app.storage.save_table(table_id, table_name, new_state)
    display.render_message(f"Column {col_name!r} added to {table_name!r}.")


# export / import

@cli.command("export")
@click.argument("table_name")
@click.option(
    "-o",
    "--output",
    default=None,
    help="Output file path. Prints to stdout if omitted.",
)
@click.pass_context
def export_cmd(ctx: click.Context, table_name: str, output: str | None) -> None:
    """Export a table to JSON."""
    app: Ctx = ctx.obj
    try:
        _, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    schema = engine.read_schema(doc)
    rows = engine.list_rows(doc)

    payload = {
        "table": schema.table_name,
        "schema": schema.to_dict(),
        "rows": [{"id": rid, **rdata} for rid, rdata in rows],
    }
    json_str = json.dumps(payload, indent=2, default=str)

    if output:
        Path(output).write_text(json_str, encoding="utf-8")
        display.render_message(f"Exported to {output}")
    else:
        click.echo(json_str)


@cli.command("import")
@click.argument("table_name")
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def import_cmd(ctx: click.Context, table_name: str, file: str) -> None:
    app: Ctx = ctx.obj
    try:
        table_id, state = app.storage.load_table_state(table_name)
    except KeyError:
        display.render_error(f"Table {table_name!r} not found.")
        raise SystemExit(1)

    raw = Path(file).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        display.render_error(f"Invalid JSON: {e}")
        raise SystemExit(1)

    doc = engine.load_doc(state)
    imported = 0
    for row_obj in payload.get("rows", []):
        # Strip the id field if present, insert fresh
        row_obj.pop("id", None)
        try:
            engine.insert_row(doc, row_obj)
            imported += 1
        except (ValueError, TypeError) as e:
            display.render_error(f"Skipping row: {e}")

    new_state = engine.serialize_doc(doc)
    app.storage.save_table(table_id, table_name, new_state)
    display.render_message(f"Imported {imported} rows into {table_name!r}.")


# sync commands

@cli.group()
def sync() -> None:
    """Peer-to-peer sync commands."""


@sync.command("start")
@click.option("--host", default="0.0.0.0", help="Bind address.")
@click.option("--port", default=9876, type=int, help="Bind port.")
@click.pass_context
def sync_start(ctx: click.Context, host: str, port: int) -> None:
    """Start the sync server (foreground)."""
    from shelf.sync import start_server

    app: Ctx = ctx.obj
    try:
        asyncio.run(start_server(app.storage, host, port))
    except KeyboardInterrupt:
        display.render_message("Sync server stopped.")


@sync.command("add-peer")
@click.argument("address")
@click.pass_context
def sync_add_peer(ctx: click.Context, address: str) -> None:
    app: Ctx = ctx.obj
    parts = address.rsplit(":", 1)
    if len(parts) != 2:
        display.render_error("Address must be host:port")
        raise SystemExit(1)
    host = parts[0]
    try:
        port = int(parts[1])
    except ValueError:
        display.render_error("Port must be a number")
        raise SystemExit(1)

    app.storage.add_peer(host, port)
    display.render_message(f"Peer {address} registered.")


@sync.command("remove-peer")
@click.argument("address")
@click.pass_context
def sync_remove_peer(ctx: click.Context, address: str) -> None:
    app: Ctx = ctx.obj
    parts = address.rsplit(":", 1)
    if len(parts) != 2:
        display.render_error("Address must be host:port")
        raise SystemExit(1)
    host = parts[0]
    try:
        port = int(parts[1])
    except ValueError:
        display.render_error("Port must be a number")
        raise SystemExit(1)

    app.storage.remove_peer(host, port)
    display.render_message(f"Peer {address} removed.")


@sync.command("status")
@click.pass_context
def sync_status(ctx: click.Context) -> None:
    """Show registered peers."""
    app: Ctx = ctx.obj
    peers = app.storage.list_peers()
    if not peers:
        display.render_message("No peers registered.", style="yellow")
        return
    from rich.table import Table as RichTable

    t = RichTable(title="Peers")
    t.add_column("Host")
    t.add_column("Port")
    t.add_column("Last Sync")
    for p in peers:
        t.add_row(p.host, str(p.port), str(p.last_sync or "never"))
    display.console.print(t)


@sync.command("now")
@click.pass_context
def sync_now(ctx: click.Context) -> None:
    """Trigger sync with all registered peers."""
    from shelf.sync import sync_with_peer

    app: Ctx = ctx.obj
    peers = app.storage.list_peers()
    if not peers:
        display.render_message("No peers registered.", style="yellow")
        return

    total = 0
    for peer in peers:
        try:
            count = asyncio.run(sync_with_peer(app.storage, peer.host, peer.port))
            display.render_message(
                f"Synced {count} table(s) with {peer.host}:{peer.port}"
            )
            total += count
        except Exception as e:
            display.render_error(
                f"Failed to sync with {peer.host}:{peer.port}: {e}"
            )

    display.render_message(f"Sync complete. {total} table(s) synced.")
