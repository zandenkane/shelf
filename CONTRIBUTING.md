# contributing

Python 3.10+. `pip install -e .[dev]` for dev dependencies.

The CRDT engine is in src/shelf/engine.py. If you want to add a new column type, that's where it goes. Storage is SQLite via src/shelf/storage.py. The sync protocol is TCP-based, defined in src/shelf/sync.py.

Tests: `pytest`
