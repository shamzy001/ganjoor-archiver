## Why

Ganjoor (ganjoor.net) is the largest online archive of classical and modern Persian poetry, but it has no offline mode — a lost internet connection means no poetry. This tool creates a permanent local copy of the full corpus (~300 poets, ~500k–700k verses) queryable via SQLite and browsable via an Obsidian vault, using the site's public REST API at the strict 1 req/s rate the volunteer-run site requires.

## What Changes

- **New project from scratch** — no existing code to modify.
- Introduces an async crawl CLI (`python main.py crawl`) that archives the full Ganjoor corpus into a local SQLite database across three resumable phases.
- Introduces an export command (`python main.py export`) that renders the database into a navigable Obsidian Markdown vault with full YAML frontmatter, era tags, and verse formatting.
- Introduces supporting commands: `status` (progress dashboard), `retry-failed` (re-attempts permanently-failed requests).
- Introduces a strict 1 req/s rate limiter and exponential backoff (5 s / 15 s / 45 s) to protect the volunteer-run host.

## Capabilities

### New Capabilities

- `api-client`: Async HTTP client wrapping `https://api.ganjoor.net` — enforces 1 req/s rate limit, retries 429/5xx with exponential backoff, logs permanent failures.
- `crawl-pipeline`: Three-phase crawl — Phase 1 discovers poets, Phase 2 walks the category tree (BFS), Phase 3 fetches poem verses. Each phase is independently resumable.
- `sqlite-storage`: SQLite schema and async upsert helpers for poets, categories, poems, verses, and failures. `fetched_at IS NULL` is the universal resume signal.
- `obsidian-export`: Renders the database into a Markdown vault — full category tree mirrored as folders, Jinja2 templates, YAML frontmatter with era classification, blockquote verse formatting with hemistich pairing.
- `cli-interface`: `argparse` CLI with four subcommands (`crawl`, `export`, `status`, `retry-failed`) and a common `--db PATH` flag.

### Modified Capabilities

*(None — this is a new project.)*

## Impact

- **New dependencies**: `httpx[asyncio]`, `aiosqlite`, `jinja2`, `python-slugify`, `tqdm`
- **External API**: `https://api.ganjoor.net` (read-only, public, no auth required)
- **Local artefacts produced**: `ganjoor.db` (SQLite, ~1–2 GB full corpus), `vault/` (Markdown files), `failures.log`
- **No write-back to the API** — purely read/archive.
- Estimated full-corpus crawl time: 24–36 hours at 1 req/s.