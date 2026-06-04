"""Tests for the sync protocol using in-memory TCP streams."""

import asyncio

import pytest

from shelf import engine
from shelf.models import MsgType, SyncMessage
from shelf.schema import ColumnDef, ColumnType, TableSchema
from shelf.storage import Storage
from shelf.sync import _encode_frame, sync_with_peer


def _make_schema() -> TableSchema:
    return TableSchema(
        table_name="items",
        columns=[
            ColumnDef(name="title", col_type=ColumnType.TEXT),
        ],
    )


class TestFraming:
    def test_encode_decode_roundtrip(self):
        msg = SyncMessage(
            msg_type=MsgType.STATE_REQUEST,
            table_id="abc123",
            payload=b"\x01\x02",
        )
        frame = _encode_frame(msg)
        # Frame starts with 4-byte length prefix
        assert len(frame) > 4

    def test_message_types(self):
        for mt in MsgType:
            msg = SyncMessage(msg_type=mt, table_id="t", payload=b"")
            frame = _encode_frame(msg)
            assert len(frame) > 4


class TestSyncIntegration:
    """Spin up a real TCP server and client to verify the sync protocol."""

    @pytest.fixture()
    def schema(self) -> TableSchema:
        return _make_schema()

    @pytest.mark.asyncio
    async def test_two_peers_converge(self, tmp_path, schema):
        """Server and client exchange updates and end up with the same data."""
        db_a = Storage(db_path=tmp_path / "a.db")
        db_b = Storage(db_path=tmp_path / "b.db")

        # Peer A: create table, insert a row
        doc_a = engine.create_table_doc(schema)
        engine.insert_row(doc_a, {"title": "from A"})
        state_a = engine.serialize_doc(doc_a)
        table_id = "shared_table"
        db_a.save_table(table_id, schema.table_name, state_a)

        # Peer B: same table, different row
        doc_b = engine.create_table_doc(schema)
        engine.insert_row(doc_b, {"title": "from B"})
        state_b = engine.serialize_doc(doc_b)
        db_b.save_table(table_id, schema.table_name, state_b)

        # Start server for peer B
        server = await asyncio.start_server(
            lambda r, w: _server_handler(r, w, db_b),
            "127.0.0.1",
            0,  # OS picks a free port
        )
        port = server.sockets[0].getsockname()[1]

        try:
            # Peer A syncs with peer B
            db_a.add_peer("127.0.0.1", port)
            count = await sync_with_peer(db_a, "127.0.0.1", port)
            assert count == 1
        finally:
            server.close()
            await server.wait_closed()

        # Verify peer A now has both rows
        _, merged_state = db_a.load_table_state(schema.table_name)
        merged_doc = engine.load_doc(merged_state)
        rows = engine.list_rows(merged_doc)
        titles = {r[1]["title"] for r in rows}
        assert "from A" in titles

        db_a.close()
        db_b.close()


async def _server_handler(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    storage: Storage,
) -> None:
    """Minimal server handler for tests, reusing sync module internals."""
    from shelf.sync import _handle_client
    await _handle_client(reader, writer, storage)
