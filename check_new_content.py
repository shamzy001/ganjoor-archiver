"""Check for new poets/categories and poem count mismatches against the API."""
import asyncio
import sqlite3
import sys
import httpx
from tqdm import tqdm

DB = "smoke.db"
BASE = "https://api.ganjoor.net"
CONCURRENCY = 8
RATE_DELAY = 0.15


async def fetch(client, sem, url):
    async with sem:
        await asyncio.sleep(RATE_DELAY)
        try:
            r = await client.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"_error": str(e), "_url": url}


async def main():
    sys.stdout.reconfigure(encoding="utf-8")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    db_poet_ids = {r[0] for r in conn.execute("SELECT id FROM poets")}
    db_cat_ids  = {r[0] for r in conn.execute("SELECT id FROM categories")}
    db_poem_counts = {r[0]: r[1] for r in conn.execute("SELECT cat_id, COUNT(*) FROM poems GROUP BY cat_id")}
    conn.close()

    sem = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient() as client:
        # --- Check poets ---
        print("Fetching poet list from API...")
        poets_data = await fetch(client, sem, f"{BASE}/api/ganjoor/poets")
        if "_error" in poets_data:
            print(f"ERROR fetching poets: {poets_data['_error']}")
            return

        api_poet_ids = {p["id"] for p in poets_data}
        new_poets = [p for p in poets_data if p["id"] not in db_poet_ids]
        removed_poets = db_poet_ids - api_poet_ids

        print(f"API poets: {len(api_poet_ids)}  |  DB poets: {len(db_poet_ids)}")
        if new_poets:
            print(f"  NEW poets ({len(new_poets)}):")
            for p in new_poets:
                print(f"    id={p['id']}  {p.get('name', '')}  {p.get('fullUrl', '')}")
        else:
            print("  No new poets.")
        if removed_poets:
            print(f"  Poets in DB but not on API: {removed_poets}")

        # --- Check categories (BFS from each poet's root cat) ---
        print(f"\nWalking category trees for all {len(api_poet_ids)} poets...")

        root_cat_ids = [p["rootCatId"] for p in poets_data if p.get("rootCatId")]
        queue = list(root_cat_ids)
        visited = set(root_cat_ids)
        new_cats = []
        poem_mismatches = []
        api_poem_total = 0

        with tqdm(desc="Categories", unit="cat") as pbar:
            while queue:
                batch = queue[:CONCURRENCY * 4]
                queue = queue[CONCURRENCY * 4:]

                tasks = [
                    asyncio.create_task(
                        fetch(client, sem, f"{BASE}/api/ganjoor/cat/{cid}?poems=true&cat=true")
                    )
                    for cid in batch
                ]
                results = await asyncio.gather(*tasks)
                pbar.update(len(batch))

                for result in results:
                    if "_error" in result:
                        continue
                    cat = result.get("cat") or {}
                    cat_id = cat.get("id")
                    if cat_id is None:
                        continue

                    if cat_id not in db_cat_ids:
                        new_cats.append({
                            "id": cat_id,
                            "title": cat.get("title", ""),
                            "full_url": cat.get("fullUrl", ""),
                        })

                    api_count = len(cat.get("poems") or [])
                    api_poem_total += api_count
                    db_count = db_poem_counts.get(cat_id, 0)
                    if api_count != db_count:
                        poem_mismatches.append({
                            "cat_id": cat_id,
                            "full_url": cat.get("fullUrl", ""),
                            "db": db_count,
                            "api": api_count,
                            "diff": api_count - db_count,
                        })

                    for child in (cat.get("children") or []):
                        child_id = child["id"]
                        if child_id not in visited:
                            visited.add(child_id)
                            queue.append(child_id)

    db_poem_total = sum(db_poem_counts.values())

    print(f"\nAPI categories visited : {len(visited)}  |  DB categories: {len(db_cat_ids)}")
    if new_cats:
        print(f"  NEW categories ({len(new_cats)}):")
        for c in new_cats:
            print(f"    id={c['id']}  {c['full_url']}")
    else:
        print("  No new categories.")

    print(f"\nAPI total poems : {api_poem_total:,}")
    print(f"DB  total poems : {db_poem_total:,}")
    print(f"Difference      : {api_poem_total - db_poem_total:+,}")
    if poem_mismatches:
        print(f"\n  Poem count mismatches ({len(poem_mismatches)} categories):")
        for m in sorted(poem_mismatches, key=lambda x: -abs(x["diff"])):
            tag = "MISSING" if m["diff"] > 0 else "EXTRA"
            print(f"    [{tag}] cat={m['cat_id']}  db={m['db']}  api={m['api']}  {m['full_url']}")
    else:
        print("  No poem count mismatches.")

    if not new_poets and not new_cats and not poem_mismatches:
        print("\nCollection is up to date.")
    else:
        print("\nRe-run Phase 1+2+3 + export to pull in any changes.")


asyncio.run(main())