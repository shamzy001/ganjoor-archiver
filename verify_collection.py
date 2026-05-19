"""Walk every category in the API and compare poem counts against the DB."""
import asyncio
import sqlite3
import sys
import httpx
from tqdm import tqdm

DB = "smoke.db"
BASE = "https://api.ganjoor.net"
CONCURRENCY = 8
RATE_DELAY = 0.15  # seconds between requests per worker


async def fetch_cat(client: httpx.AsyncClient, sem: asyncio.Semaphore, cat_id: int) -> dict | None:
    async with sem:
        await asyncio.sleep(RATE_DELAY)
        try:
            r = await client.get(f"{BASE}/api/ganjoor/cat/{cat_id}?poems=true&cat=false", timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e), "cat_id": cat_id}


async def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    cat_rows = conn.execute("SELECT id, poet_id FROM categories").fetchall()
    cat_ids = [r["id"] for r in cat_rows]

    # DB poem count per category
    db_counts = {}
    for r in conn.execute("SELECT cat_id, COUNT(*) AS n FROM poems GROUP BY cat_id"):
        db_counts[r["cat_id"]] = r["n"]

    print(f"Checking {len(cat_ids)} categories against API (concurrency={CONCURRENCY})...")

    sem = asyncio.Semaphore(CONCURRENCY)
    mismatches = []
    errors = []
    api_total = 0

    async with httpx.AsyncClient() as client:
        tasks = {asyncio.create_task(fetch_cat(client, sem, cid)): cid for cid in cat_ids}
        with tqdm(total=len(tasks), unit="cat") as pbar:
            for coro in asyncio.as_completed(tasks):
                result = await coro
                pbar.update(1)
                if result is None or "error" in result:
                    errors.append(result)
                    continue
                cat = result.get("cat") or {}
                cat_id = cat.get("id")
                if cat_id is None:
                    continue
                api_count = len(cat.get("poems") or [])
                api_total += api_count
                db_count = db_counts.get(cat_id, 0)
                if api_count != db_count:
                    mismatches.append({
                        "cat_id": cat_id,
                        "title": cat.get("title", ""),
                        "full_url": cat.get("fullUrl", ""),
                        "db": db_count,
                        "api": api_count,
                        "diff": api_count - db_count,
                    })

    conn.close()

    db_total = sum(db_counts.values())

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"\nAPI total poems : {api_total:,}")
    print(f"DB  total poems : {db_total:,}")
    print(f"Difference      : {api_total - db_total:+,}")
    print(f"Errors fetching : {len(errors)}")
    if errors:
        for e in errors[:5]:
            print(f"  {e}")

    if not mismatches:
        print("Collection is complete — all category poem counts match the API.")
    else:
        total_missing = sum(m["diff"] for m in mismatches if m["diff"] > 0)
        total_extra   = sum(-m["diff"] for m in mismatches if m["diff"] < 0)
        print(f"Mismatches found: {len(mismatches)} categories")
        print(f"  Missing from DB: {total_missing} poems")
        print(f"  Extra in DB:     {total_extra} poems")
        print()
        for m in sorted(mismatches, key=lambda x: -abs(x["diff"])):
            tag = "MISSING" if m["diff"] > 0 else "EXTRA"
            print(f"  [{tag:7s}] cat={m['cat_id']}  db={m['db']}  api={m['api']}  {m['full_url']}")


asyncio.run(main())