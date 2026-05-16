## 1. Project Scaffold

- [ ] 1.1 Replace stub `main.py` with argparse skeleton (four subcommands, no logic yet)
- [ ] 1.2 Create `ganjoor/` package with empty `__init__.py`, `models.py`, `era.py`, `client.py`, `db.py`, `crawler.py`, `exporter.py`
- [ ] 1.3 Create `ganjoor/templates/` directory with placeholder `.j2` files: `vault_index.md.j2`, `poet_index.md.j2`, `book_index.md.j2`, `poem.md.j2`
- [ ] 1.4 Write `requirements.txt` with `httpx[asyncio]`, `aiosqlite`, `jinja2`, `python-slugify`, `tqdm`
- [ ] 1.5 Install dependencies into `.venv` and verify imports succeed

## 2. Data Models

- [ ] 2.1 Implement `Poet`, `Category`, `Poem`, `Verse` dataclasses in `ganjoor/models.py`
- [ ] 2.2 Implement `classify_era(birth_year_in_lh)` in `ganjoor/era.py` with the eight era bands

## 3. SQLite Storage

- [ ] 3.1 Implement `init_db(db_path)` in `ganjoor/db.py` — creates all five tables with `CREATE TABLE IF NOT EXISTS` and enables `PRAGMA foreign_keys = ON`
- [ ] 3.2 Implement `upsert_poet(conn, poet_dict)` — `INSERT OR REPLACE` into `poets`
- [ ] 3.3 Implement `upsert_category(conn, cat_dict, poet_id, parent_id)` — `INSERT OR REPLACE` into `categories`
- [ ] 3.4 Implement `upsert_poem(conn, poem_dict, cat_id, poet_id)` — `INSERT OR REPLACE` into `poems`
- [ ] 3.5 Implement `replace_verses(conn, poem_id, verses)` — `DELETE` then bulk `INSERT` in one transaction; sets `poems.fetched_at` in the same transaction
- [ ] 3.6 Implement `log_failure(conn, entity_type, entity_id, url, error)` — `INSERT` into `failures`

## 4. API Client

- [ ] 4.1 Implement `GanjoorClient.__aenter__` / `__aexit__` that creates/closes a single `httpx.AsyncClient`
- [ ] 4.2 Implement private `_get(url)` coroutine: enforces 1.0 s rate limit via module-level timestamp + `asyncio.sleep`, retries 429/5xx with backoff [5, 15, 45] s, returns `None` after 3 failures
- [ ] 4.3 Implement `get_poets()` → `GET /api/ganjoor/poets`
- [ ] 4.4 Implement `get_poet(id)` → `GET /api/ganjoor/poet/{id}`
- [ ] 4.5 Implement `get_category(id)` → `GET /api/ganjoor/cat/{id}?poems=true&cat=true`
- [ ] 4.6 Implement `get_poem(id)` → `GET /api/ganjoor/poem/{id}?verses=true`
- [ ] 4.7 Smoke-test client in isolation: call `get_poets()` and print first poet's name

## 5. Crawl Pipeline — Phase 1

- [ ] 5.1 Implement `run_phase1(db_path)` in `ganjoor/crawler.py`: call `get_poets()`, upsert all poets, then for each poet with `fetched_at IS NULL` call `get_poet(id)` to get full detail + root category
- [ ] 5.2 Upsert root category for each poet into `categories` with `fetched_at = NULL`
- [ ] 5.3 Set `poets.fetched_at = now` after successful poet detail fetch
- [ ] 5.4 On failure: call `log_failure()` and continue; show tqdm progress bar

## 6. Crawl Pipeline — Phase 2

- [ ] 6.1 Implement `run_phase2(db_path)` in `ganjoor/crawler.py`: seed BFS queue from `SELECT id FROM categories WHERE fetched_at IS NULL`
- [ ] 6.2 For each category: call `get_category(id)`, upsert all child `cats` (fetched_at NULL), upsert all poem stubs (fetched_at NULL)
- [ ] 6.3 Set `categories.fetched_at = now` after successful walk
- [ ] 6.4 On failure: call `log_failure()` and continue; show tqdm progress bar

## 7. Crawl Pipeline — Phase 3

- [ ] 7.1 Implement `run_phase3(db_path)` in `ganjoor/crawler.py`: query `SELECT id FROM poems WHERE fetched_at IS NULL`
- [ ] 7.2 For each poem: call `get_poem(id)`, then call `replace_verses()` (atomic transaction)
- [ ] 7.3 On failure: call `log_failure()` and continue; show tqdm progress bar

## 8. Jinja2 Templates

- [ ] 8.1 Write `vault_index.md.j2`: frontmatter-free, one `## {era}` section per era, wiki-links to each poet's `_index`
- [ ] 8.2 Write `poet_index.md.j2`: poet name heading, English name / era / birth year line, description, `## Books` section with wiki-links to direct child categories
- [ ] 8.3 Write `book_index.md.j2`: category title heading, optional `## Sub-sections` with wiki-links to child categories, optional `## Poems` with wiki-links to poems in this category
- [ ] 8.4 Write `poem.md.j2`: YAML frontmatter block (`title`, `poet`, `era`, `source`, `tags`), poem title heading, blockquote verse body

## 9. Verse Renderer

- [ ] 9.1 Implement `render_verses(verses: list[Verse]) -> list[str]` in `ganjoor/exporter.py`: iterate in `v_order`, pair position-0+1 into `> {right}  |  {left}`, render position-2/3 alone as `> {text}`

## 10. Obsidian Exporter

- [ ] 10.1 Implement `build_category_path(cat_id, db) -> Path` — walk `parent_id` chain to reconstruct the full relative folder path for a category
- [ ] 10.2 Implement `export_poem(poem, poet, verses, cat_path, vault_path, force)` — render `poem.md.j2` and write to correct path; handle slug collision with `-{id}` suffix
- [ ] 10.3 Implement `export_category_index(cat, poet, children, poems, cat_path, vault_path, force)` — render `book_index.md.j2`
- [ ] 10.4 Implement `export_poet_index(poet, top_cats, vault_path, force)` — render `poet_index.md.j2`
- [ ] 10.5 Implement `export_vault_index(poets_by_era, vault_path, force)` — render `vault_index.md.j2`
- [ ] 10.6 Implement top-level `run_export(db_path, vault_path, poet_filter, force)` — orchestrates 10.1–10.5, prints summary of files written / skipped

## 11. CLI Wiring

- [ ] 11.1 Wire `crawl` subcommand: parse `--phase` and `--db`, call `asyncio.run(run_crawl(phase, db_path))`
- [ ] 11.2 Wire `export` subcommand: parse `--vault`, `--poet`, `--force`, `--db`, call `asyncio.run(run_export(...))`
- [ ] 11.3 Wire `status` subcommand: parse `--estimate`, print counts table, optionally print ETA
- [ ] 11.4 Wire `retry-failed` subcommand: read `failures` where `retried=0`, re-attempt each, mark `retried=1`
- [ ] 11.5 Verify `python main.py --help` and each subcommand's `--help` output is correct

## 12. Smoke Test

- [ ] 12.1 Run `python main.py crawl --phase 1` — verify at least 200 poets appear in DB
- [ ] 12.2 Run `python main.py status` — verify counts are non-zero
- [ ] 12.3 Run `python main.py crawl --phase 2` for a small poet (add a `--poet-id` debug flag if needed) — verify categories and poem stubs appear
- [ ] 12.4 Run `python main.py crawl --phase 3` on that poet's poems — verify verses are in DB
- [ ] 12.5 Run `python main.py export --poet {name_en} --vault smoke-vault/` — verify folder structure, frontmatter, verse formatting
- [ ] 12.6 Open `smoke-vault/` in Obsidian and confirm: wiki-links resolve, verses render in blockquotes, era tags appear correctly
