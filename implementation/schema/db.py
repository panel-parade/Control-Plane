"""SQLite connection and schema initialisation for the Work Register."""

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)  # explicit transactions only
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    _add_item_type_column_if_missing(conn)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def _add_item_type_column_if_missing(conn: sqlite3.Connection) -> None:
    """Migrate a pre-#32 work_items table: legacy rows get item_type NULL (flagged, not inferred)."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'work_items'").fetchone()
    if exists is None:
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(work_items)")}
    if "item_type" not in columns:
        conn.execute(
            """ALTER TABLE work_items ADD COLUMN item_type TEXT CHECK (item_type IN (
                   'Decision', 'Validation', 'Execution', 'Observation', 'Exception'))""")
