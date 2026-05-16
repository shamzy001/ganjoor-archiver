import aiosqlite
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS poets (
            id              INTEGER PRIMARY KEY,
            name            TEXT NOT NULL,
            full_url        TEXT NOT NULL DEFAULT '',
            nickname        TEXT,
            description     TEXT,
            birth_year_in_lh INTEGER,
            death_year_in_lh INTEGER,
            image_url       TEXT,
            root_cat_id     INTEGER,
            fetched_at      TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY,
            poet_id     INTEGER NOT NULL,
            parent_id   INTEGER,
            title       TEXT NOT NULL DEFAULT '',
            url_slug    TEXT NOT NULL DEFAULT '',
            full_url    TEXT NOT NULL DEFAULT '',
            fetched_at  TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS poems (
            id          INTEGER PRIMARY KEY,
            cat_id      INTEGER NOT NULL,
            poet_id     INTEGER NOT NULL,
            title       TEXT NOT NULL,
            url_slug    TEXT,
            full_url    TEXT NOT NULL DEFAULT '',
            fetched_at  TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS verses (
            id              INTEGER PRIMARY KEY,
            poem_id         INTEGER NOT NULL,
            v_order         INTEGER NOT NULL,
            verse_position  INTEGER NOT NULL,
            text            TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS failures (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id   INTEGER NOT NULL,
            url         TEXT NOT NULL,
            error       TEXT,
            created_at  TEXT NOT NULL,
            retried     INTEGER NOT NULL DEFAULT 0
        )
    """)
    await db.commit()


async def replace_verses(db: aiosqlite.Connection, poem_id: int, verses: list[dict]) -> None:
    """Delete all existing verses for a poem and insert the fresh set atomically."""
    await db.execute("DELETE FROM verses WHERE poem_id = ?", (poem_id,))
    if verses:
        await db.executemany(
            "INSERT INTO verses (id, poem_id, v_order, verse_position, text) VALUES (?,?,?,?,?)",
            [
                (v["id"], poem_id, v["vOrder"], v["versePosition"], v["text"])
                for v in verses
            ],
        )
    await db.execute(
        "UPDATE poems SET fetched_at = ? WHERE id = ?", (_now(), poem_id)
    )
    await db.commit()


async def log_failure(
    db: aiosqlite.Connection,
    entity_type: str,
    entity_id: int,
    url: str,
    error: str,
) -> None:
    await db.execute(
        "INSERT INTO failures (entity_type, entity_id, url, error, created_at) VALUES (?,?,?,?,?)",
        (entity_type, entity_id, url, error, _now()),
    )
    await db.commit()
    with open("failures.log", "a", encoding="utf-8") as fh:
        fh.write(f"{_now()}\t{entity_type}\t{entity_id}\t{url}\t{error}\n")
