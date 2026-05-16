## ADDED Requirements

### Requirement: Four subcommands via argparse
The CLI entry point (`main.py`) SHALL expose four subcommands using `argparse` subparsers: `crawl`, `export`, `status`, and `retry-failed`. Invoking `python main.py` without a subcommand SHALL print help and exit with code 1.

#### Scenario: No subcommand prints help
- **WHEN** `python main.py` is run with no arguments
- **THEN** usage help is printed and the process exits with code 1

#### Scenario: Unknown subcommand prints error
- **WHEN** `python main.py bogus` is run
- **THEN** an error message is printed and the process exits with a non-zero code

### Requirement: `crawl` subcommand
`crawl` SHALL accept `--phase {1,2,3,all}` (default: `all`) and `--db PATH` (default: `ganjoor.db`). It SHALL run the specified crawl phase(s) and display a `tqdm` progress bar per phase.

#### Scenario: Default crawl runs all phases
- **WHEN** `python main.py crawl` is run
- **THEN** phases 1, 2, and 3 execute in sequence against `ganjoor.db`

#### Scenario: Single-phase crawl runs only that phase
- **WHEN** `python main.py crawl --phase 2` is run
- **THEN** only Phase 2 executes

#### Scenario: Custom DB path is respected
- **WHEN** `python main.py crawl --db archive/ganjoor.db` is run
- **THEN** the database is read from and written to `archive/ganjoor.db`

### Requirement: `export` subcommand
`export` SHALL accept `--vault PATH` (default: `vault/`), `--poet NAME_EN`, `--force`, and `--db PATH` (default: `ganjoor.db`). After export, it SHALL print a summary of files written and files skipped.

#### Scenario: Export writes vault to default path
- **WHEN** `python main.py export` is run after a completed crawl
- **THEN** Markdown files are written under `vault/`

#### Scenario: --force overwrites existing files
- **WHEN** `python main.py export --force` is run
- **THEN** all files are written regardless of existing content

#### Scenario: --poet limits export scope
- **WHEN** `python main.py export --poet rumi` is run
- **THEN** only `vault/poets/rumi/` is written or updated

### Requirement: `status` subcommand
`status` SHALL print a human-readable table showing total/fetched counts for poets, categories, poems, and verses, plus the count of entries in the `failures` table.

When `--estimate` is provided, it SHALL additionally print the estimated remaining crawl time at 1 req/s.

#### Scenario: Status shows counts
- **WHEN** `python main.py status` is run
- **THEN** a table with rows for poets, categories, poems, verses, and failures is printed to stdout

#### Scenario: --estimate shows ETA
- **WHEN** `python main.py status --estimate` is run
- **THEN** an additional line shows estimated remaining time in hours and minutes

### Requirement: `retry-failed` subcommand
`retry-failed` SHALL read all rows from the `failures` table where `retried = 0`, re-attempt each entity's API fetch, and mark `retried = 1` on both success and permanent failure.

#### Scenario: Successfully retried entity is removed from failures backlog
- **WHEN** `retry-failed` is run and a previously-failed poem now returns HTTP 200
- **THEN** the poem's data is stored and `failures.retried` is set to 1

#### Scenario: Still-failing entity is marked retried=1
- **WHEN** `retry-failed` is run and the entity still fails all 3 retries
- **THEN** `failures.retried` is set to 1 and a new failure row is NOT inserted (no infinite loop)

### Requirement: All subcommands use `asyncio.run()`
Each subcommand handler SHALL be an async coroutine invoked via `asyncio.run()` in `main.py`. No sync wrappers around async code are permitted.

#### Scenario: Event loop is created once per invocation
- **WHEN** any subcommand is run
- **THEN** `asyncio.run()` is called exactly once for the top-level coroutine
