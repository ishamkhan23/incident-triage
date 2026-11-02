"""
store.py - incident history in SQLite.

The fingerprint column is UNIQUE, so running the tool twice on the same
log won't create (or alert on) the same incident twice.
"""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint  TEXT UNIQUE NOT NULL,
    kind         TEXT NOT NULL,
    service      TEXT NOT NULL,
    code         TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    summary      TEXT NOT NULL,
    details      TEXT,
    status       TEXT NOT NULL DEFAULT 'open',
    detected_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at      TEXT NOT NULL DEFAULT (datetime('now')),
    log_file    TEXT,
    lines       INTEGER,
    errors      INTEGER,
    new_incidents INTEGER
);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_new(conn, incidents):
    """Insert incidents; return only the ones that weren't already stored."""
    new = []
    for inc in incidents:
        cur = conn.execute(
            """INSERT OR IGNORE INTO incidents
               (fingerprint, kind, service, code, started_at, summary, details)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (inc.fingerprint, inc.kind, inc.service, inc.code,
             inc.started_at.isoformat(), inc.summary, json.dumps(inc.details)),
        )
        if cur.rowcount == 1:
            new.append(inc)
    conn.commit()
    return new


def log_run(conn, log_file, stats, new_count):
    conn.execute(
        "INSERT INTO runs (log_file, lines, errors, new_incidents) VALUES (?, ?, ?, ?)",
        (log_file, stats["lines"], stats["errors"], new_count),
    )
    conn.commit()
