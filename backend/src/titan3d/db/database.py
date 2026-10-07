"""SQLite connection factory and schema.

Each operation opens a short-lived connection, so the API (threads) and the
worker processes can share one database file. WAL mode lets readers proceed
while a worker writes progress.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from collections.abc import Generator


SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dems (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL CHECK (source IN ('builtin', 'upload')),
    status      TEXT NOT NULL CHECK (status IN ('processing', 'ready', 'failed')),
    mosaic_path TEXT,
    files_json  TEXT,
    info_json   TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    dem_id           TEXT NOT NULL REFERENCES dems (id),
    status           TEXT NOT NULL CHECK (status IN (
                         'queued', 'running', 'completed', 'failed',
                         'cancelled', 'interrupted')),
    scenario_json    TEXT NOT NULL,
    provenance_json  TEXT,
    grid_json        TEXT,
    parent_job_id    TEXT REFERENCES jobs (id) ON DELETE SET NULL,
    pid              INTEGER,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT,
    heartbeat_at     TEXT,
    sim_t            REAL NOT NULL DEFAULT 0,
    t_end            REAL NOT NULL,
    steps            INTEGER NOT NULL DEFAULT 0,
    frames           INTEGER NOT NULL DEFAULT 0,
    elapsed_s        REAL NOT NULL DEFAULT 0,
    eta_s            REAL,
    hmax             REAL,
    umax             REAL,
    runout           REAL,
    area             REAL,
    vol_in_domain    REAL,
    vol_out          REAL,
    released_m3      REAL,
    error            TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS jobs_created ON jobs (created_at);

CREATE TABLE IF NOT EXISTS job_frames (
    job_id     TEXT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    k          INTEGER NOT NULL,
    stats_json TEXT NOT NULL,
    PRIMARY KEY (job_id, k)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with WAL, a busy timeout and foreign keys enabled."""
    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def session(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Connection inside a transaction; committed on success, rolled back on error."""
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    """Create the schema if needed and record its version."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
    finally:
        conn.close()
