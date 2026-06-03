"""Rich-based terminal rendering for shelf output."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shelf.schema import TableSchema

console = Console()


def render_table(
    schema: TableSchema,
    rows: list[tuple[str, dict[str, Any]]],
    *,
    show_id: bool = True,
) -> None:
    table = Table(title=schema.table_name, show_lines=True)

    if show_id:
        table.add_column("id", style="dim", no_wrap=True, max_width=12)

    for col in schema.columns:
        table.add_column(col.name)

    for row_id, row_data in rows:
        values: list[str] = []
        if show_id:
            values.append(row_id[:12])
        for col in schema.columns:
            val = row_data.get(col.name, "")
            values.append(_format_cell(val))
        table.add_row(*values)

    console.print(table)


def render_row_detail(
    row_id: str,
    row_data: dict[str, Any],
) -> None:
    """Print a single row as a key-value panel."""
    lines: list[str] = [f"[bold]id:[/bold] {row_id}"]
    for key, value in row_data.items():
        lines.append(f"[bold]{key}:[/bold] {_format_cell(value)}")
    panel = Panel("\n".join(lines), title="Row Detail")
    console.print(panel)


def render_schema(schema: TableSchema) -> None:
    """Print column definitions as a Rich table."""
    table = Table(title=f"Schema: {schema.table_name}")
    table.add_column("Column")
    table.add_column("Type")
    table.add_column("Nullable")
    table.add_column("Default")

    for col in schema.columns:
        table.add_row(
            col.name,
            col.col_type.value,
            str(col.nullable),
            _format_cell(col.default),
        )
    console.print(table)


def render_tables(tables: list[dict[str, Any]]) -> None:
    """Print a list of tables as a Rich table."""
    table = Table(title="Tables")
    table.add_column("Name")
    table.add_column("Rows", justify="right")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Created")

    for t in tables:
        row_count = str(t.get("rows", ""))
        table.add_row(t["name"], row_count, t["id"][:12], str(t["created_at"]))
    console.print(table)


def render_message(text: str, *, style: str = "green") -> None:
    console.print(f"[{style}]{text}[/{style}]")


def render_error(text: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]Error:[/bold red] {text}")


def _format_cell(value: Any) -> str:
    if value is None:
        return "[dim]null[/dim]"
    return str(value)
