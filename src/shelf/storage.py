"""SQLite persistence layer for shelf tables, updates, and peers."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from shelf.models import PeerInfo, TableMeta

# Default database location
DEFAULT_DB_DIR = Path.home() / ".shelf"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "shelf.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tables (
    table_id   TEXT PRIMARY KEY,
    table_name TEXT NOT NULL UNIQUE,
    crdt_state BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS updates (
    update_id   TEXT PRIMARY KEY,
    table_id    TEXT NOT NULL,
    update_data BLOB NOT NULL,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    applied     INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (table_id) REFERENCES tables(table_id)
);

CREATE TABLE IF NOT EXISTS peers (
    peer_id    TEXT PRIMARY KEY,
    host       TEXT NOT NULL,
    port       INTEGER NOT NULL,
    last_sync  TEXT,
    UNIQUE(host, port)
);
"""


class Storage:
    """Thin wrapper around a SQLite database for shelf persistence."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = DEFAULT_DB_PATH
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    # Table operations

    def save_table(
        self,
        table_id: str,
        table_name: str,
        crdt_state: bytes,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO tables (table_id, table_name, crdt_state)
            VALUES (?, ?, ?)
            ON CONFLICT(table_id)
            DO UPDATE SET crdt_state = excluded.crdt_state
            """,
            (table_id, table_name, crdt_state),
        )
        self._conn.commit()

    def load_table_state(self, table_name: str) -> tuple[str, bytes]:
        """Return (table_id, crdt_state) for the given table name.

        Raises KeyError if the table does not exist.
        """
        row = self._conn.execute(
            "SELECT table_id, crdt_state FROM tables WHERE table_name = ?",
            (table_name,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Table {table_name!r} not found")
        return row[0], row[1]

    def load_table_state_by_id(self, table_id: str) -> bytes:
        """Return the crdt_state blob for a table ID."""
        row = self._conn.execute(
            "SELECT crdt_state FROM tables WHERE table_id = ?",
            (table_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Table ID {table_id!r} not found")
        return row[0]

    def list_tables(self) -> list[TableMeta]:
        rows = self._conn.execute(
            "SELECT table_id, table_name, created_at FROM tables ORDER BY created_at"
        ).fetchall()
        result: list[TableMeta] = []
        for table_id, name, created_at in rows:
            result.append(
                TableMeta(
                    id=table_id,
                    name=name,
                    created_at=datetime.fromisoformat(created_at),
                )
            )
        return result

    def table_exists(self, table_name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM tables WHERE table_name = ?", (table_name,)
        ).fetchone()
        return row is not None

    def drop_table(self, table_name: str) -> None:
        """Delete a table and all its associated updates."""
        row = self._conn.execute(
            "SELECT table_id FROM tables WHERE table_name = ?", (table_name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Table {table_name!r} not found")
        table_id = row[0]
        self._conn.execute("DELETE FROM updates WHERE table_id = ?", (table_id,))
        self._conn.execute("DELETE FROM tables WHERE table_id = ?", (table_id,))
        self._conn.commit()

    def all_table_ids(self) -> list[str]:
        """Return every table_id in the database."""
        rows = self._conn.execute("SELECT table_id FROM tables").fetchall()
        return [r[0] for r in rows]

    # Update log

    def save_update(self, table_id: str, update_data: bytes) -> str:
        """Persist a single CRDT update and return its ID."""
        update_id = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO updates (update_id, table_id, update_data) VALUES (?, ?, ?)",
            (update_id, table_id, update_data),
        )
        self._conn.commit()
        return update_id

    # Peer management

    def add_peer(self, host: str, port: int) -> str:
        """Register a sync peer. Returns the peer ID."""
        peer_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO peers (peer_id, host, port)
            VALUES (?, ?, ?)
            ON CONFLICT(host, port) DO UPDATE SET peer_id = excluded.peer_id
            """,
            (peer_id, host, port),
        )
        self._conn.commit()
        return peer_id

    def list_peers(self) -> list[PeerInfo]:
        rows = self._conn.execute(
            "SELECT peer_id, host, port, last_sync FROM peers"
        ).fetchall()
        result: list[PeerInfo] = []
        for peer_id, host, port, last_sync in rows:
            result.append(
                PeerInfo(
                    id=peer_id,
                    host=host,
                    port=port,
                    last_sync=(
                        datetime.fromisoformat(last_sync) if last_sync else None
                    ),
                )
            )
        return result

    def remove_peer(self, host: str, port: int) -> None:
        self._conn.execute(
            "DELETE FROM peers WHERE host = ? AND port = ?", (host, port)
        )
        self._conn.commit()

    def update_peer_sync_time(self, host: str, port: int) -> None:
        self._conn.execute(
            "UPDATE peers SET last_sync = datetime('now') WHERE host = ? AND port = ?",
            (host, port),
        )
        self._conn.commit()

    # Lifecycle

    def close(self) -> None:
        self._conn.close()
