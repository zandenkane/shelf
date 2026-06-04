"""Tests for the shared data models."""

from datetime import datetime, timezone

from shelf.models import MsgType, PeerInfo, SyncMessage, TableMeta


class TestTableMeta:
    def test_default_created_at_is_utc(self):
        meta = TableMeta(id="t1", name="stuff")
        assert meta.created_at.tzinfo is not None or isinstance(meta.created_at, datetime)

    def test_default_row_count_is_zero(self):
        meta = TableMeta(id="t1", name="stuff")
        assert meta.row_count == 0

    def test_fields_assigned(self):
        ts = datetime(2026, 6, 1, tzinfo=timezone.utc)
        meta = TableMeta(id="abc", name="items", created_at=ts, row_count=42)
        assert meta.id == "abc"
        assert meta.name == "items"
        assert meta.created_at == ts
        assert meta.row_count == 42


class TestPeerInfo:
    def test_no_last_sync(self):
        peer = PeerInfo(id="p1", host="10.0.0.1", port=9876)
        assert peer.last_sync is None

    def test_with_last_sync(self):
        ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
        peer = PeerInfo(id="p1", host="10.0.0.1", port=9876, last_sync=ts)
        assert peer.last_sync == ts


class TestMsgType:
    def test_values(self):
        assert MsgType.STATE_REQUEST == 1
        assert MsgType.STATE_VECTOR == 2
        assert MsgType.UPDATE == 3
        assert MsgType.DONE == 4


class TestSyncMessage:
    def test_default_payload_empty(self):
        msg = SyncMessage(msg_type=MsgType.DONE, table_id="t1")
        assert msg.payload == b""

    def test_fields_assigned(self):
        msg = SyncMessage(
            msg_type=MsgType.UPDATE,
            table_id="t1",
            payload=b"\x01\x02",
        )
        assert msg.msg_type == MsgType.UPDATE
        assert msg.table_id == "t1"
        assert msg.payload == b"\x01\x02"
