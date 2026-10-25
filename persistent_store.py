"""Persistent JSON snapshots for macro/news feeds.

Uses DATABASE_URL (Postgres) when configured, otherwise RADAR_CACHE_DB_PATH or a
local SQLite file. SQLite on ephemeral hosting is not durable; diagnostics says so.
"""
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


def _connect():
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        import psycopg
        conn = psycopg.connect(url, connect_timeout=8)
        conn.execute("""CREATE TABLE IF NOT EXISTS radar_cache (
            cache_key TEXT PRIMARY KEY, payload JSONB NOT NULL,
            updated_utc TEXT NOT NULL
        )""")
        conn.commit()
        return conn, True
    path = os.getenv("RADAR_CACHE_DB_PATH", "/tmp/natural_gas_cache.sqlite3")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=8)
    conn.execute("""CREATE TABLE IF NOT EXISTS radar_cache (
        cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_utc TEXT NOT NULL
    )""")
    conn.commit()
    return conn, False


def put_json(key: str, payload: dict) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    conn, postgres = _connect()
    try:
        if postgres:
            conn.execute(
                "INSERT INTO radar_cache(cache_key,payload,updated_utc) VALUES(%s,%s,%s) "
                "ON CONFLICT(cache_key) DO UPDATE SET payload=EXCLUDED.payload, updated_utc=EXCLUDED.updated_utc",
                (key, json.dumps(payload), stamp),
            )
        else:
            conn.execute(
                "INSERT INTO radar_cache(cache_key,payload,updated_utc) VALUES(?,?,?) "
                "ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload, updated_utc=excluded.updated_utc",
                (key, json.dumps(payload), stamp),
            )
        conn.commit()
    finally:
        conn.close()


def get_json(key: str):
    conn, postgres = _connect()
    try:
        cur = conn.execute("SELECT payload, updated_utc FROM radar_cache WHERE cache_key=" + ("%s" if postgres else "?"), (key,))
        row = cur.fetchone()
        if not row:
            return None
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return {"payload": payload, "updated_utc": row[1]}
    finally:
        conn.close()
