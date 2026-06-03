"""Shared data classes used across shelf modules."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TableMeta:
    """Lightweight metadata about a stored table."""

    id: str
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    row_count: int = 0


@dataclass
class PeerInfo:

    id: str
    host: str
    port: int
    last_sync: datetime | None = None


class MsgType(enum.IntEnum):

    STATE_REQUEST = 1
    STATE_VECTOR = 2
    UPDATE = 3
    DONE = 4


@dataclass
class SyncMessage:
    """A single message exchanged during peer sync."""

    msg_type: MsgType
    table_id: str
    payload: bytes = b""
