"""Peer-to-peer sync over TCP using asyncio and msgpack framing.

Protocol:
1. Initiator sends STATE_REQUEST for each table (with its state vector).
2. Responder replies with UPDATE (the diff the initiator is missing).
3. Initiator sends its UPDATE back so the responder also converges.
4. Both sides send DONE when finished.

Wire format: 4-byte big-endian length prefix, then msgpack-encoded message.

from __future__ import annotations

import asyncio
import struct
from typing import Any

import msgpack

from shelf import engine
from shelf.models import MsgType, SyncMessage
from shelf.storage import Storage

# Frame helpers

def _encode_frame(msg: SyncMessage) -> bytes:
    payload = msgpack.packb({
        "type": msg.msg_type.value,
        "table_id": msg.table_id,
        "payload": msg.payload,
    })
    return struct.pack("!I", len(payload)) + payload


def _decode_message(raw: dict[str, Any]) -> SyncMessage:
    return SyncMessage(
        msg_type=MsgType(raw["type"]),
        table_id=raw["table_id"],
        payload=raw["payload"],
    )


async def _read_frame(
    reader: asyncio.StreamReader,
) -> SyncMessage | None:
    """Read one length-prefixed frame from the stream."""
    length_bytes = await reader.readexactly(4)
    length = struct.unpack("!I", length_bytes)[0]
    data = await reader.readexactly(length)
    raw = msgpack.unpackb(data, raw=False)
    return _decode_message(raw)


async def _write_frame(
    writer: asyncio.StreamWriter,
    msg: SyncMessage,
) -> None:
    writer.write(_encode_frame(msg))
    await writer.drain()


# Server (responder side)

async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    storage: Storage,
) -> None:
    try:
        while True:
            try:
                msg = await _read_frame(reader)
            except asyncio.IncompleteReadError:
                break
            if msg is None:
                break

            if msg.msg_type == MsgType.DONE:
                break

            if msg.msg_type == MsgType.STATE_REQUEST:
                # Client sent its state vector; compute what it is missing.
                table_id = msg.table_id
                remote_state = msg.payload
                try:
                    local_state_blob = storage.load_table_state_by_id(table_id)
                except KeyError:
                    # We don't have this table, send empty update
                    await _write_frame(
                        writer,
                        SyncMessage(MsgType.UPDATE, table_id, b""),
                    )
                    continue

                doc = engine.load_doc(local_state_blob)
                diff = engine.get_diff_update(doc, remote_state)
                await _write_frame(
                    writer,
                    SyncMessage(MsgType.UPDATE, table_id, diff),
                )

            elif msg.msg_type == MsgType.UPDATE:
                # Client is sending us data we are missing.
                if msg.payload:
                    table_id = msg.table_id
                    try:
                        local_state_blob = storage.load_table_state_by_id(table_id)
                        doc = engine.load_doc(local_state_blob)
                    except KeyError:
                        continue
                    engine.apply_update(doc, msg.payload)
                    new_state = engine.serialize_doc(doc)
                    storage.save_table(table_id, "", new_state)

    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def start_server(
    storage: Storage,
    host: str = "0.0.0.0",
    port: int = 9876,
) -> None:

    async def handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await _handle_client(reader, writer, storage)

    server = await asyncio.start_server(handler, host, port)
    addr = server.sockets[0].getsockname() if server.sockets else (host, port)
    print(f"Sync server listening on {addr[0]}:{addr[1]}")
    async with server:
        await server.serve_forever()


# Client (initiator side)

async def sync_with_peer(
    storage: Storage,
    host: str,
    port: int,
) -> int:
    """Connect to a peer and sync all local tables. Returns the number of
    tables synced.
    reader, writer = await asyncio.open_connection(host, port)
    synced = 0
    try:
        table_ids = storage.all_table_ids()
        for table_id in table_ids:
            local_blob = storage.load_table_state_by_id(table_id)
            doc = engine.load_doc(local_blob)

            # Step 1: send our state vector
            state_vec = engine.get_state_vector(doc)
            await _write_frame(
                writer,
                SyncMessage(MsgType.STATE_REQUEST, table_id, state_vec),
            )

            # Step 2: receive their diff update
            resp = await _read_frame(reader)
            if resp and resp.msg_type == MsgType.UPDATE and resp.payload:
                engine.apply_update(doc, resp.payload)

            # Step 3: send our diff back to them
            # Re-read the remote state from their perspective (use empty state
            # as a conservative fallback; in practice the responder already
            # sent us everything it had).
            our_update = engine.serialize_doc(doc)
            await _write_frame(
                writer,
                SyncMessage(MsgType.UPDATE, table_id, our_update),
            )

            # Persist merged state
            new_state = engine.serialize_doc(doc)
            # We need the table name to save; read it from the doc.
            table_schema = engine.read_schema(doc)
            storage.save_table(table_id, table_schema.table_name, new_state)
            synced += 1

        # Signal completion
        await _write_frame(
            writer,
            SyncMessage(MsgType.DONE, "", b""),
        )
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    storage.update_peer_sync_time(host, port)
    return synced
