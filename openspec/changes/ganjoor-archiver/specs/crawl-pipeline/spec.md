## ADDED Requirements

### Requirement: Three-phase crawl with independent resumability
The system SHALL crawl the corpus in three ordered phases. Each phase SHALL be independently resumable: killing the process and restarting SHALL continue from the last completed entity without duplicating or losing data.

#### Scenario: Phase 1 discovers all poets
- **WHEN** `crawl --phase 1` is run on an empty database
- **THEN** all poets from `GET /api/ganjoor/poets` are upserted into the `poets` table and each poet's root category is upserted into `categories` with `fetched_at = NULL`

#### Scenario: Phase 1 resumes correctly
- **WHEN** `crawl --phase 1` is run a second time after partial completion
- **THEN** only poets whose `fetched_at IS NULL` are re-fetched; already-fetched poets are skipped

#### Scenario: Phase 2 walks the full category tree
- **WHEN** `crawl --phase 2` is run after Phase 1
- **THEN** every category reachable from any root category is upserted (BFS), including all sub-categories and poem stubs

#### Scenario: Phase 2 resumes after interruption
- **WHEN** Phase 2 is interrupted mid-walk and restarted
- **THEN** the BFS queue is re-seeded from `SELECT id FROM categories WHERE fetched_at IS NULL`; already-walked categories are skipped

#### Scenario: Phase 3 fetches verses for all poems
- **WHEN** `crawl --phase 3` is run after Phase 2
- **THEN** every poem with `fetched_at IS NULL` has its verses fetched and inserted in a single atomic transaction

#### Scenario: Phase 3 resumes after interruption
- **WHEN** Phase 3 is interrupted and restarted
- **THEN** poems with `fetched_at IS NOT NULL` are skipped; the interrupted poem (if any) is cleanly re-fetched

### Requirement: Atomic verse insertion per poem
For each poem in Phase 3, the system SHALL delete all existing verses and insert the full set in a single `BEGIN / COMMIT` transaction. `poems.fetched_at` SHALL be set inside the same transaction as the final step.

#### Scenario: Crash during verse insertion leaves no partial state
- **WHEN** the process is killed mid-transaction during verse insertion
- **THEN** on restart the poem's `fetched_at` is still NULL and the poem is re-fetched cleanly

### Requirement: Permanent failures are logged and skipped
If an entity (poet, category, or poem) fails all 3 retries, the system SHALL:
1. Insert a row into the `failures` table.
2. Append a line to `failures.log`.
3. Continue processing the next entity.

#### Scenario: Failed category is logged and skipped
- **WHEN** `GET /api/ganjoor/cat/{id}` returns 5xx three times
- **THEN** a row is inserted into `failures` for that category, a line is appended to `failures.log`, and the crawl continues with the next queued category

### Requirement: `--phase all` runs phases 1 → 2 → 3 sequentially
When invoked with `--phase all` (the default), the crawler SHALL run all three phases in order, stopping between phases only if a fatal error occurs.

#### Scenario: Default crawl completes full corpus
- **WHEN** `crawl` is run with no `--phase` flag
- **THEN** phases 1, 2, and 3 execute in sequence

### Requirement: Progress bar per phase
Each phase SHALL display a `tqdm` progress bar showing the count of entities processed vs. total for that phase.

#### Scenario: Progress bar updates on each entity
- **WHEN** a phase is running
- **THEN** the progress bar increments after each poet / category / poem is processed (success or permanent failure)
