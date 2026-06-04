"""Tests for the SQLite storage layer."""

from pathlib import Path

import pytest

from shelf.storage import Storage


@pytest.fixture()
def store(tmp_path: Path) -> Storage:
    return Storage(db_path=tmp_path / "test.db")


class TestTablePersistence:
    def test_save_and_load(self, store: Storage):
        blob = b"\x01\x02\x03"
        store.save_table("t1", "my_table", blob)
        tid, loaded = store.load_table_state("my_table")
        assert tid == "t1"
        assert loaded == blob

    def test_load_missing_raises(self, store: Storage):
        with pytest.raises(KeyError):
            store.load_table_state("nope")

    def test_list_tables(self, store: Storage):
        store.save_table("t1", "alpha", b"a")
        store.save_table("t2", "beta", b"b")
        tables = store.list_tables()
        names = {t.name for t in tables}
        assert names == {"alpha", "beta"}

    def test_table_exists(self, store: Storage):
        assert not store.table_exists("x")
        store.save_table("t1", "x", b"")
        assert store.table_exists("x")

    def test_drop_table(self, store: Storage):
        store.save_table("t1", "doomed", b"x")
        store.drop_table("doomed")
        assert not store.table_exists("doomed")

    def test_drop_missing_raises(self, store: Storage):
        with pytest.raises(KeyError):
            store.drop_table("ghost")

    def test_overwrite_state(self, store: Storage):
        store.save_table("t1", "tbl", b"old")
        store.save_table("t1", "tbl", b"new")
        _, loaded = store.load_table_state("tbl")
        assert loaded == b"new"


class TestPeers:
    def test_add_and_list(self, store: Storage):
        store.add_peer("127.0.0.1", 9876)
        peers = store.list_peers()
        assert len(peers) == 1
        assert peers[0].host == "127.0.0.1"
        assert peers[0].port == 9876

    def test_remove_peer(self, store: Storage):
        store.add_peer("127.0.0.1", 9876)
        store.remove_peer("127.0.0.1", 9876)
        assert len(store.list_peers()) == 0

    def test_duplicate_peer_upserts(self, store: Storage):
        store.add_peer("127.0.0.1", 9876)
        store.add_peer("127.0.0.1", 9876)
        peers = store.list_peers()
        assert len(peers) == 1


class TestUpdates:
    def test_save_update(self, store: Storage):
        store.save_table("t1", "tbl", b"state")
        uid = store.save_update("t1", b"update_data")
        assert uid  # non-empty string


class TestAllTableIds:
    def test_empty(self, store: Storage):
        assert store.all_table_ids() == []

    def test_multiple(self, store: Storage):
        store.save_table("t1", "alpha", b"a")
        store.save_table("t2", "beta", b"b")
        ids = store.all_table_ids()
        assert set(ids) == {"t1", "t2"}


class TestLoadById:
    def test_load_by_id(self, store: Storage):
        store.save_table("t1", "tbl", b"\x99")
        state = store.load_table_state_by_id("t1")
        assert state == b"\x99"

    def test_load_by_id_missing(self, store: Storage):
        with pytest.raises(KeyError):
            store.load_table_state_by_id("nope")


class TestPeerSyncTime:
    def test_update_sync_time(self, store: Storage):
        store.add_peer("10.0.0.1", 9876)
        store.update_peer_sync_time("10.0.0.1", 9876)
        peers = store.list_peers()
        assert peers[0].last_sync is not None


class TestClose:
    def test_close_does_not_error(self, store: Storage):
        store.close()
