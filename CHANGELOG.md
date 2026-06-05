# Changelog

All notable changes to shelf are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-28

### Added
- Table management: create, list, describe, and drop tables with typed column schemas.
- Row operations: add, list, get, update, delete, and count rows with Pydantic validation.
- Column operations: add new columns to existing tables with automatic backfill.
- CRDT engine backed by pycrdt (Yrs) for conflict-free merging of concurrent edits.
- Schema validation with six column types: text, integer, float, boolean, datetime, json.
- Type coercion from string inputs to native Python types.
- SQLite persistence with WAL mode at ~/.shelf/shelf.db.
- JSON export and import for table data.
- Peer sync over TCP with msgpack framed binary protocol.
- Peer management: register, list, remove, and sync with remote peers.
- Row counts displayed in `table list` output.
- Rich terminal output for tables, row details, and schema descriptions.
- Test suite covering engine, storage, schema, CLI, display, models, and sync.
- CI workflow running pytest on Python 3.10, 3.11, and 3.12.
