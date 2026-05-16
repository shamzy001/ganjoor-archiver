## ADDED Requirements

### Requirement: Five-table schema
The system SHALL create the following tables on first run if they do not exist: `poets`, `categories`, `poems`, `verses`, `failures`. Foreign key constraints SHALL be enabled via `PRAGMA foreign_keys = ON`.

#### Scenario: Schema is created on first run
- **WHEN** the database file does not exist and any CLI command is run with `--db`
- **THEN** all five tables are created and `PRAGMA foreign_keys = ON` is set

#### Scenario: Schema creation is idempotent
- **WHEN** the database already exists with all tables present
- **THEN** running schema creation again raises no error and alters no data

### Requirement: `fetched_at` is the resume signal on all entity tables
Every row in `poets`, `categories`, and `poems` SHALL have a `fetched_at TEXT` column (ISO-8601 datetime or NULL). NULL means the entity has not been fully processed. Setting `fetched_at` to the current UTC datetime is the final step of processing each entity.

#### Scenario: Newly inserted poet has fetched_at NULL
- **WHEN** a poet is upserted during Phase 1 discovery (list fetch)
- **THEN** `poets.fetched_at` is NULL until the poet's detail endpoint is successfully fetched

#### Scenario: fetched_at is set after successful category walk
- **WHEN** a category's children and poem stubs have been upserted
- **THEN** `categories.fetched_at` is set to the current UTC datetime

### Requirement: Upsert semantics for all entity tables
All inserts into `poets`, `categories`, `poems`, and `failures` SHALL use `INSERT OR REPLACE` so that re-running a phase is safe and idempotent.

#### Scenario: Re-inserting a poet does not duplicate the row
- **WHEN** a poet row is upserted twice with the same `id`
- **THEN** exactly one row exists in `poets` for that `id`

### Requirement: Verses replaced atomically per poem
Before inserting verses for a poem, the system SHALL `DELETE FROM verses WHERE poem_id = ?` and then bulk-insert all new verses, all within a single database transaction that also sets `poems.fetched_at`.

#### Scenario: Re-fetching a poem replaces its verses
- **WHEN** a poem is fetched a second time (e.g. after a prior partial fetch)
- **THEN** old verse rows are deleted and the fresh verse set is inserted; no duplicate verse rows exist

### Requirement: Poets table columns
`poets` SHALL have: `id INTEGER PRIMARY KEY`, `name TEXT`, `name_en TEXT`, `description TEXT`, `birth_year_in_lh INTEGER`, `death_year_in_lh INTEGER`, `image_url TEXT`, `fetched_at TEXT`.

#### Scenario: Poet row stores birth year for era classification
- **WHEN** a poet's detail is fetched and `birthYearInLHijri` is present in the API response
- **THEN** `birth_year_in_lh` is stored as an integer in the `poets` row

### Requirement: Categories table columns
`categories` SHALL have: `id INTEGER PRIMARY KEY`, `poet_id INTEGER`, `parent_id INTEGER`, `title TEXT`, `title_en TEXT`, `url_slug TEXT`, `fetched_at TEXT`.

#### Scenario: Root category has NULL parent_id
- **WHEN** a poet's root category is upserted
- **THEN** its `parent_id` is NULL

### Requirement: Poems table columns
`poems` SHALL have: `id INTEGER PRIMARY KEY`, `cat_id INTEGER`, `poet_id INTEGER`, `title TEXT`, `url_slug TEXT`, `source_url TEXT`, `fetched_at TEXT`.

#### Scenario: Poem stub is inserted during Phase 2 with fetched_at NULL
- **WHEN** a poem appears in a category response during Phase 2
- **THEN** the poem is upserted with `fetched_at = NULL` and verse fetch is deferred to Phase 3

### Requirement: Verses table columns
`verses` SHALL have: `id INTEGER PRIMARY KEY`, `poem_id INTEGER`, `v_order INTEGER`, `position INTEGER`, `text TEXT`.

#### Scenario: Verses are stored in v_order
- **WHEN** verses are inserted for a poem
- **THEN** each verse row has `v_order` matching its sequence position from the API response

### Requirement: Failures table columns
`failures` SHALL have: `id INTEGER PRIMARY KEY AUTOINCREMENT`, `entity_type TEXT`, `entity_id INTEGER`, `url TEXT`, `error TEXT`, `created_at TEXT`, `retried INTEGER DEFAULT 0`.

#### Scenario: Failed entity is recorded with retried=0
- **WHEN** an entity exhausts all retries
- **THEN** a row is inserted into `failures` with `retried = 0` and the error message
