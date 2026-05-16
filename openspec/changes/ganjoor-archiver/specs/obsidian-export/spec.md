## ADDED Requirements

### Requirement: Vault mirrors full category tree as filesystem folders
The system SHALL create one folder per Ganjoor category, nested to match the exact depth of the category tree. A category's folder is a child of its parent category's folder. Root categories are children of the poet's folder.

#### Scenario: Three-level category tree produces three folder levels
- **WHEN** a poet has categories A → B → C (root → child → grandchild)
- **THEN** the vault contains `poets/{poet}/a/b/c/`

#### Scenario: Poem is placed in its direct parent category's folder
- **WHEN** a poem belongs to category C
- **THEN** its Markdown file is at `poets/{poet}/a/b/c/{poem-slug}.md`

### Requirement: _index.md at every folder level
The system SHALL write a `_index.md` file in every folder: `vault/`, each poet folder, and each category folder at every depth.

#### Scenario: vault/_index.md lists all poets grouped by era
- **WHEN** the export command completes
- **THEN** `vault/_index.md` contains one section per era with Obsidian wiki-links to each poet's `_index.md`

#### Scenario: Poet _index.md includes bio and top-level category links
- **WHEN** a poet folder is created
- **THEN** `poets/{name_en}/_index.md` contains the poet's name, English name, era, birth year, description, and links to direct child categories

#### Scenario: Category _index.md lists sub-sections and poems
- **WHEN** a category folder is created
- **THEN** its `_index.md` contains links to child sub-categories (if any) and links to poems that directly belong to this category

### Requirement: Poem files have YAML frontmatter
Every poem Markdown file SHALL begin with YAML frontmatter containing `title`, `poet`, `era`, `source`, and `tags`.

#### Scenario: Poem frontmatter is well-formed YAML
- **WHEN** a poem file is written
- **THEN** the file starts with `---`, contains all required fields, and ends the block with `---`

#### Scenario: tags contains slugified poet name and era
- **WHEN** a poem file is written for Hafez (name_en = "hafez", era = "ilkhanid-timurid")
- **THEN** `tags` includes `hafez` and `ilkhanid-timurid`

### Requirement: Verse blockquote formatting
All verses SHALL be wrapped in Markdown blockquotes (`>`). Adjacent position-0 (right hemistich) and position-1 (left hemistich) verses SHALL be paired on one line separated by `  |  ` (two spaces, pipe, two spaces). Position-2 (single line) and position-3 (prose/paragraph) verses SHALL appear alone.

#### Scenario: Hemistich pair is rendered on one line
- **WHEN** a poem has verse at v_order=0 with position=0 (right) and v_order=1 with position=1 (left)
- **THEN** the rendered line is `> {right_text}  |  {left_text}`

#### Scenario: Single-line verse renders alone
- **WHEN** a verse has position=2
- **THEN** the rendered line is `> {text}` with no pairing

#### Scenario: Prose verse renders alone
- **WHEN** a verse has position=3
- **THEN** the rendered line is `> {text}` with no pairing

### Requirement: Era classification from birth year
The system SHALL classify each poet into one of eight era labels based on `birth_year_in_lh` using the following bands:

| Birth year (LH) | Era label |
|---|---|
| NULL | `unknown-era` |
| < 300 | `early-islamic` |
| 300–499 | `khorasani` |
| 500–699 | `seljuk` |
| 700–899 | `ilkhanid-timurid` |
| 900–1099 | `safavid` |
| 1100–1299 | `qajar` |
| ≥ 1300 | `modern` |

#### Scenario: Hafez (born ~727 LH) is classified as ilkhanid-timurid
- **WHEN** `classify_era(727)` is called
- **THEN** it returns `"ilkhanid-timurid"`

#### Scenario: Poet with unknown birth year gets unknown-era
- **WHEN** `classify_era(None)` is called
- **THEN** it returns `"unknown-era"`

### Requirement: Filesystem-safe slugs
Folder and file names SHALL be generated with `python-slugify` using `-` as the separator. Persian titles SHALL be slugified using their ASCII `title_en` field if available; otherwise the Persian title is passed directly to `slugify` which strips non-ASCII characters.

#### Scenario: Poet folder name is derived from name_en
- **WHEN** a poet with `name_en = "Hafez"` is exported
- **THEN** their folder is `poets/hafez/`

#### Scenario: Duplicate poem slugs in same folder get id suffix
- **WHEN** two poems in the same category produce the same slug
- **THEN** the second file is named `{slug}-{poem_id}.md`

### Requirement: --force flag controls overwrite behaviour
Without `--force`, existing poem files SHALL be skipped. With `--force`, all files SHALL be overwritten.

#### Scenario: Existing file is skipped without --force
- **WHEN** `export` is run twice without `--force` and a poem file already exists
- **THEN** the existing file is not modified and the export reports it as skipped

#### Scenario: Existing file is overwritten with --force
- **WHEN** `export` is run with `--force`
- **THEN** all files are written regardless of whether they already exist

### Requirement: --poet filter exports a single poet's subtree
When `--poet NAME_EN` is provided, the system SHALL export only that poet's folder (and update `vault/_index.md` to reference them).

#### Scenario: Single-poet export creates only that poet's files
- **WHEN** `export --poet hafez` is run
- **THEN** only `vault/poets/hafez/` and its contents are created or updated
