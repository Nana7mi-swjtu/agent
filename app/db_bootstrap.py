from __future__ import annotations

import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def ensure_database_exists(
    database_url: str,
    *,
    charset: str = "utf8mb4",
    collation: str = "utf8mb4_unicode_ci",
) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("mysql"):
        raise RuntimeError("Auto-create database only supports MySQL URLs")

    db_name = url.database
    if not db_name:
        return
    if not _DB_NAME_RE.match(db_name):
        raise ValueError("Database name contains unsupported characters")

    server_url = url.set(database="mysql")
    engine = create_engine(server_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE DATABASE IF NOT EXISTS "
                    f"`{db_name}` CHARACTER SET {charset} COLLATE {collation}"
                )
            )
    finally:
        engine.dispose()
