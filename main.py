import argparse
import asyncio
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Archive the Ganjoor poetry corpus to SQLite and Obsidian vault",
    )
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("crawl", help="Crawl the Ganjoor API")
    p.add_argument("--phase", choices=["1", "2", "3", "all"], default="all")
    p.add_argument("--db", default="ganjoor.db", metavar="PATH")

    p = sub.add_parser("export", help="Render the DB as an Obsidian vault")
    p.add_argument("--vault", default="vault", metavar="PATH")
    p.add_argument("--poet", default=None, metavar="NAME_EN",
                   help="Export only this poet (use the URL slug, e.g. 'hafez')")
    p.add_argument("--force", action="store_true", help="Overwrite existing files")
    p.add_argument("--db", default="ganjoor.db", metavar="PATH")

    p = sub.add_parser("status", help="Show crawl progress")
    p.add_argument("--estimate", action="store_true",
                   help="Print estimated remaining time at 1 req/s")
    p.add_argument("--db", default="ganjoor.db", metavar="PATH")

    p = sub.add_parser("retry-failed", help="Re-attempt logged failures")
    p.add_argument("--db", default="ganjoor.db", metavar="PATH")

    args = parser.parse_args()

    if args.cmd is None:
        parser.print_help()
        sys.exit(1)

    if args.cmd == "crawl":
        asyncio.run(_crawl(args))
    elif args.cmd == "export":
        from ganjoor.exporter import export_vault
        export_vault(args.db, args.vault, args.poet, args.force)
    elif args.cmd == "status":
        asyncio.run(_status(args))
    elif args.cmd == "retry-failed":
        asyncio.run(_retry_failed(args))


async def _crawl(args) -> None:
    from ganjoor.crawler import run_crawl
    await run_crawl(args.phase, args.db)


async def _status(args) -> None:
    import aiosqlite
    from ganjoor.db import init_db

    async with aiosqlite.connect(args.db) as db:
        await init_db(db)
        async with db.execute("""
            SELECT
                (SELECT COUNT(*) FROM poets)                                   AS total_poets,
                (SELECT COUNT(*) FROM poets      WHERE fetched_at IS NOT NULL) AS done_poets,
                (SELECT COUNT(*) FROM categories)                              AS total_cats,
                (SELECT COUNT(*) FROM categories WHERE fetched_at IS NOT NULL) AS done_cats,
                (SELECT COUNT(*) FROM poems)                                   AS total_poems,
                (SELECT COUNT(*) FROM poems      WHERE fetched_at IS NOT NULL) AS done_poems,
                (SELECT COUNT(*) FROM verses)                                  AS total_verses,
                (SELECT COUNT(*) FROM failures   WHERE retried = 0)            AS pending_failures
        """) as cur:
            r = await cur.fetchone()

    print(f"{'Poets':<14} {r[1]:>8} / {r[0]:<8}")
    print(f"{'Categories':<14} {r[3]:>8} / {r[2]:<8}")
    print(f"{'Poems':<14} {r[5]:>8} / {r[4]:<8}")
    print(f"{'Verses':<14} {r[6]:>8}")
    print(f"{'Failures':<14} {r[7]:>8} pending")

    if args.estimate:
        remaining = (r[0] - r[1]) + (r[2] - r[3]) + (r[4] - r[5])
        h, rem = divmod(remaining, 3600)
        m = rem // 60
        print(f"\nEst. remaining: ~{h}h {m}m  ({remaining:,} requests at 1 req/s)")


async def _retry_failed(args) -> None:
    from datetime import datetime, timezone

    import aiosqlite

    from ganjoor.client import GanjoorClient
    from ganjoor.db import init_db, replace_verses

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async with aiosqlite.connect(args.db) as db:
        await init_db(db)

        async with db.execute(
            "SELECT id, entity_type, entity_id, url FROM failures WHERE retried = 0"
        ) as cur:
            failures = [(r[0], r[1], r[2], r[3]) async for r in cur]

        if not failures:
            print("No pending failures.")
            return

        print(f"Retrying {len(failures)} failure(s)...")

        async with GanjoorClient() as client:
            for fid, etype, eid, url in failures:
                success = False

                if etype == "poet":
                    detail = await client.get_poet(eid)
                    if detail:
                        pd, cat = detail["poet"], detail["cat"]
                        await db.execute(
                            """UPDATE poets SET name=?, full_url=?, description=?,
                               birth_year_in_lh=?, death_year_in_lh=?,
                               image_url=?, root_cat_id=?, fetched_at=? WHERE id=?""",
                            (pd["name"], pd["fullUrl"], pd.get("description"),
                             pd.get("birthYearInLHijri"), pd.get("deathYearInLHijri"),
                             pd.get("imageUrl"), pd.get("rootCatId"), now(), eid),
                        )
                        await db.execute(
                            """INSERT INTO categories
                               (id, poet_id, parent_id, title, url_slug, full_url, fetched_at)
                               VALUES (?,?,NULL,?,?,?,NULL)
                               ON CONFLICT(id) DO UPDATE SET
                                   title=excluded.title,
                                   url_slug=excluded.url_slug,
                                   full_url=excluded.full_url""",
                            (cat["id"], eid, cat["title"],
                             cat.get("urlSlug", ""), cat.get("fullUrl", "")),
                        )
                        await db.commit()
                        success = True

                elif etype == "category":
                    result = await client.get_category(eid)
                    if result:
                        cat = result["cat"]
                        poet_id = result["poet"]["id"]
                        for child in (cat.get("children") or []):
                            await db.execute(
                                """INSERT INTO categories
                                   (id, poet_id, parent_id, title, url_slug, full_url, fetched_at)
                                   VALUES (?,?,?,?,?,?,NULL)
                                   ON CONFLICT(id) DO NOTHING""",
                                (child["id"], poet_id, eid,
                                 child.get("title", ""), child.get("urlSlug", ""),
                                 child.get("fullUrl", "")),
                            )
                        for p in (cat.get("poems") or []):
                            slug = p.get("urlSlug") or str(p["id"])
                            fu = cat["fullUrl"].rstrip("/") + "/" + slug
                            await db.execute(
                                """INSERT INTO poems
                                   (id, cat_id, poet_id, title, url_slug, full_url, fetched_at)
                                   VALUES (?,?,?,?,?,?,NULL)
                                   ON CONFLICT(id) DO NOTHING""",
                                (p["id"], eid, poet_id, p["title"], p.get("urlSlug"), fu),
                            )
                        await db.execute(
                            "UPDATE categories SET fetched_at=? WHERE id=?", (now(), eid)
                        )
                        await db.commit()
                        success = True

                elif etype == "poem":
                    result = await client.get_poem(eid)
                    if result:
                        fu = result.get("fullUrl", "")
                        if fu:
                            await db.execute(
                                "UPDATE poems SET full_url=? WHERE id=?", (fu, eid)
                            )
                        await replace_verses(db, eid, result.get("verses") or [])
                        success = True

                await db.execute("UPDATE failures SET retried=1 WHERE id=?", (fid,))
                await db.commit()
                print(f"  {etype:10} {eid:8}  {'OK' if success else 'STILL FAILING'}")


if __name__ == "__main__":
    main()
