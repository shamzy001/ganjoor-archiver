## Context

Ganjoor's public REST API (`https://api.ganjoor.net`) exposes a hierarchical corpus: poets → categories (arbitrary depth) → poems → verses. The data model is a tree, not a flat list. The volunteer-run server enforces a hard rate limit of 1 request/second; exceeding it returns 429 errors and risks getting the IP blocked.

The project has no prior codebase. It will be a standalone Python package with a CLI entry point at `main.py`, an internal `ganjoor/` package, and a SQLite file as the durable store.

## Goals / Non-Goals

**Goals:**
- Full, resumable crawl of the entire corpus at ≤1 req/s
- SQLite as the authoritative offline store (regenerable vault without re-crawl)
- Human-readable Obsidian vault that mirrors the logical structure of the corpus
- Safe re-runs: upsert everything, never duplicate, never lose partial progress

**Non-Goals:**
- Poet images, audio files, user comments, transliteration
- Write-back to the API
- A local web server / search interface
- Incremental sync after full crawl (out of scope for now)

## Decisions

### D1: Async I/O (`asyncio` + `httpx` + `aiosqlite`) over sync
**Rationale:** Even at 1 req/s the crawl runs for 24–36 hours. Async lets the rate-limit sleep yield the event loop, and `aiosqlite` keeps DB writes non-blocking. A sync implementation with `time.sleep` would work but wastes a thread on sleeping.  
**Alternative considered:** `requests` + `sqlite3` in a thread — simpler but offers no parallelism if we ever want to relax the rate limit per-endpoint.

### D2: SQLite as primary store, not PostgreSQL or flat files
**Rationale:** No server to run, no schema migrations needed during development, perfect for a single-user archival tool. The corpus (~500k verses) fits comfortably in SQLite (< 2 GB). Queries for status, resume, and export are all simple SELECTs with no joins deeper than 2 levels.  
**Alternative considered:** JSON files per poem — good for portability, bad for queryability and atomic updates.

### D3: Three explicit crawl phases (not one monolithic pass)
**Rationale:** Separating poet discovery, category walking, and verse fetching makes each phase independently resumable and testable. A monolithic pass would require complex bookkeeping to restart mid-tree.  
**Alternative considered:** Single DFS pass — simpler logic but non-resumable mid-run.

### D4: `fetched_at IS NULL` as the universal resume signal
**Rationale:** A single nullable timestamp column on every entity row is the simplest possible checkpoint. On restart, re-query `WHERE fetched_at IS NULL` — no separate state file, no journal, no checkpoint table needed.  
**Alternative considered:** A separate `progress` table — more flexible but unnecessary for this access pattern.

### D5: BFS (queue) for category walking, not recursive DFS
**Rationale:** BFS avoids Python recursion-depth limits on deep category trees. The queue is seeded from the DB at phase start, making it trivially resumable: kill the process, restart, re-seed the queue from `SELECT id FROM categories WHERE fetched_at IS NULL`.  
**Alternative considered:** Recursive DFS — elegant but hits Python's default recursion limit for trees deeper than ~1000 nodes.

### D6: Full category tree mirrored in vault filesystem
**Rationale:** A 1:1 mapping between Ganjoor's category hierarchy and the vault's folder structure eliminates any hidden flattening rule. Users navigating the Obsidian sidebar see exactly the same organisation as on ganjoor.net.  
**Alternative considered:** Flatten all sub-categories into a top-level book folder — simpler to implement but loses structural information for works like Masnavi (6 Daftars × N chapters).

### D7: Jinja2 templates for vault rendering, not f-strings
**Rationale:** Jinja2 separates presentation from logic, allows whitespace control, and makes template iteration easy without touching Python code.  
**Alternative considered:** f-strings / `str.format` — fast but unmaintainable for multi-section Markdown documents.

### D8: `INSERT OR REPLACE` (UPSERT) for all entity tables
**Rationale:** Idempotent re-runs require that re-inserting a row that already exists is safe. `INSERT OR REPLACE` achieves this without a `SELECT` first. Verses are the exception: they are deleted and re-inserted as a group within a single transaction to avoid stale verse rows from a partially-completed earlier fetch.  
**Alternative considered:** `INSERT OR IGNORE` — ignores re-crawled updates; `ON CONFLICT DO UPDATE` — verbose for tables with many columns.

## Risks / Trade-offs

- **IP ban if rate limit is breached** → Mitigation: hard-coded 1.0 s floor in `_get()`, no concurrent requests.
- **API schema changes** → Mitigation: store raw JSON fields by name; if a field disappears, the column gets NULL rather than a crash. Log schema mismatches.
- **Long crawl interrupted by power loss** → Mitigation: `fetched_at` checkpoint + atomic verse transactions ensure at most one poem worth of re-fetch on restart.
- **Duplicate poem filenames in vault** (two poems with identical slugs in the same category) → Mitigation: append `-{id}` suffix if slug already exists in the output folder.
- **SQLite concurrent writes** → Non-issue: the crawler is single-process, single-writer.

## Migration Plan

New project — no migration required.

## Open Questions

*(None — all decisions are resolved in this document.)*
