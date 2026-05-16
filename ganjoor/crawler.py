from collections import deque
from datetime import datetime, timezone

import aiosqlite
from tqdm import tqdm

from .client import GanjoorClient
from .db import init_db, log_failure, replace_verses


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_phase1(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)

        async with GanjoorClient() as client:
            print("Phase 1 — fetching poets list...")
            poets = await client.get_poets()
            if poets is None:
                raise RuntimeError("Failed to fetch /api/ganjoor/poets after retries")

            # Seed poet + root-category stubs from the list response
            for p in poets:
                await db.execute(
                    """
                    INSERT INTO poets
                        (id, name, full_url, nickname, description,
                         birth_year_in_lh, death_year_in_lh, image_url,
                         root_cat_id, fetched_at)
                    VALUES (?,?,?,?,?,?,?,?,?,NULL)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        p["id"], p["name"], p["fullUrl"], p.get("nickname"),
                        p.get("description"), p.get("birthYearInLHijri"),
                        p.get("deathYearInLHijri"), p.get("imageUrl"),
                        p.get("rootCatId"),
                    ),
                )
                root_cat_id = p.get("rootCatId")
                if root_cat_id:
                    await db.execute(
                        """
                        INSERT INTO categories
                            (id, poet_id, parent_id, title, url_slug, full_url, fetched_at)
                        VALUES (?,?,NULL,'','','',NULL)
                        ON CONFLICT(id) DO NOTHING
                        """,
                        (root_cat_id, p["id"]),
                    )
            await db.commit()
            print(f"  Seeded {len(poets)} poets and root-category stubs")

            # Fetch full detail for every un-fetched poet
            async with db.execute(
                "SELECT id FROM poets WHERE fetched_at IS NULL"
            ) as cur:
                poet_ids = [row[0] async for row in cur]

            for poet_id in tqdm(poet_ids, desc="  Poet details", unit="poet"):
                detail = await client.get_poet(poet_id)
                if detail is None:
                    await log_failure(
                        db, "poet", poet_id,
                        f"https://api.ganjoor.net/api/ganjoor/poet/{poet_id}",
                        "max retries exceeded",
                    )
                    continue

                pd = detail["poet"]
                cat = detail["cat"]

                await db.execute(
                    """
                    UPDATE poets SET
                        name=?, full_url=?, nickname=?, description=?,
                        birth_year_in_lh=?, death_year_in_lh=?,
                        image_url=?, root_cat_id=?, fetched_at=?
                    WHERE id=?
                    """,
                    (
                        pd["name"], pd["fullUrl"], pd.get("nickname"),
                        pd.get("description"), pd.get("birthYearInLHijri"),
                        pd.get("deathYearInLHijri"), pd.get("imageUrl"),
                        pd.get("rootCatId"), _now(), poet_id,
                    ),
                )
                # Update root category with proper data now that we have it
                await db.execute(
                    """
                    INSERT INTO categories
                        (id, poet_id, parent_id, title, url_slug, full_url, fetched_at)
                    VALUES (?,?,NULL,?,?,?,NULL)
                    ON CONFLICT(id) DO UPDATE SET
                        title    = excluded.title,
                        url_slug = excluded.url_slug,
                        full_url = excluded.full_url
                    """,
                    (cat["id"], poet_id, cat["title"],
                     cat.get("urlSlug", ""), cat.get("fullUrl", "")),
                )
                await db.commit()


async def run_phase2(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)

        async with GanjoorClient() as client:
            async with db.execute(
                "SELECT id FROM categories WHERE fetched_at IS NULL"
            ) as cur:
                queue: deque[int] = deque([row[0] async for row in cur])

            print(f"Phase 2 — walking categories (BFS, {len(queue)} seeds)...")
            pbar = tqdm(desc="  Categories", unit="cat")

            while queue:
                cat_id = queue.popleft()
                pbar.total = (pbar.n or 0) + len(queue) + 1

                result = await client.get_category(cat_id)
                if result is None:
                    await log_failure(
                        db, "category", cat_id,
                        f"https://api.ganjoor.net/api/ganjoor/cat/{cat_id}",
                        "max retries exceeded",
                    )
                    pbar.update(1)
                    continue

                poet = result["poet"]
                cat  = result["cat"]
                poet_id = poet["id"]

                # Upsert child categories and push them onto the BFS queue
                for child in (cat.get("children") or []):
                    await db.execute(
                        """
                        INSERT INTO categories
                            (id, poet_id, parent_id, title, url_slug, full_url, fetched_at)
                        VALUES (?,?,?,?,?,?,NULL)
                        ON CONFLICT(id) DO UPDATE SET
                            title    = COALESCE(excluded.title,    title),
                            url_slug = COALESCE(excluded.url_slug, url_slug),
                            full_url = COALESCE(excluded.full_url, full_url)
                        """,
                        (
                            child["id"], poet_id, cat_id,
                            child.get("title", ""),
                            child.get("urlSlug", ""),
                            child.get("fullUrl", ""),
                        ),
                    )
                    queue.append(child["id"])

                # Upsert poem stubs (no verses yet)
                for p in (cat.get("poems") or []):
                    slug = p.get("urlSlug") or str(p["id"])
                    full_url = cat["fullUrl"].rstrip("/") + "/" + slug
                    await db.execute(
                        """
                        INSERT INTO poems
                            (id, cat_id, poet_id, title, url_slug, full_url, fetched_at)
                        VALUES (?,?,?,?,?,?,NULL)
                        ON CONFLICT(id) DO NOTHING
                        """,
                        (p["id"], cat_id, poet_id, p["title"], p.get("urlSlug"), full_url),
                    )

                await db.execute(
                    "UPDATE categories SET fetched_at=? WHERE id=?", (_now(), cat_id)
                )
                await db.commit()
                pbar.update(1)

            pbar.close()


async def run_phase3(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await init_db(db)

        async with GanjoorClient() as client:
            async with db.execute(
                "SELECT id FROM poems WHERE fetched_at IS NULL"
            ) as cur:
                poem_ids = [row[0] async for row in cur]

            print(f"Phase 3 — fetching verses for {len(poem_ids)} poems...")

            for poem_id in tqdm(poem_ids, desc="  Poems", unit="poem"):
                result = await client.get_poem(poem_id)
                if result is None:
                    await log_failure(
                        db, "poem", poem_id,
                        f"https://api.ganjoor.net/api/ganjoor/poem/{poem_id}",
                        "max retries exceeded",
                    )
                    continue

                full_url = result.get("fullUrl", "")
                if full_url:
                    await db.execute(
                        "UPDATE poems SET full_url=? WHERE id=?", (full_url, poem_id)
                    )

                await replace_verses(db, poem_id, result.get("verses") or [])


async def run_crawl(phase: str, db_path: str) -> None:
    phases = {
        "1":   [run_phase1],
        "2":   [run_phase2],
        "3":   [run_phase3],
        "all": [run_phase1, run_phase2, run_phase3],
    }
    for fn in phases[phase]:
        await fn(db_path)
