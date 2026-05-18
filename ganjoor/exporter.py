import os
import sqlite3
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from tqdm import tqdm

from .era import classify_era
from .models import Category, Poem, Poet, Verse

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_ERA_ORDER = [
    "early-islamic", "khorasani", "seljuk", "ilkhanid-timurid",
    "safavid", "qajar", "modern", "unknown-era",
]
_WORKERS = min(8, os.cpu_count() or 4)


# ---------------------------------------------------------------------------
# Verse rendering
# ---------------------------------------------------------------------------

def render_verses(verses: list[Verse]) -> list[str]:
    """Pair adjacent right(0)+left(1) hemistiches into bayt lines."""
    lines: list[str] = []
    i = 0
    while i < len(verses):
        v = verses[i]
        if (
            v.verse_position == 0
            and i + 1 < len(verses)
            and verses[i + 1].verse_position == 1
        ):
            lines.append(f"> {v.text}  |  {verses[i + 1].text}")
            i += 2
        else:
            lines.append(f"> {v.text}")
            i += 1
    return lines


# ---------------------------------------------------------------------------
# DB row helpers
# ---------------------------------------------------------------------------

def _poet_from_row(r: sqlite3.Row) -> Poet:
    return Poet(
        id=r["id"], name=r["name"], full_url=r["full_url"],
        nickname=r["nickname"], description=r["description"],
        birth_year_in_lh=r["birth_year_in_lh"],
        death_year_in_lh=r["death_year_in_lh"],
        root_cat_id=r["root_cat_id"],
    )


def _cat_from_row(r: sqlite3.Row) -> Category:
    return Category(
        id=r["id"], poet_id=r["poet_id"], parent_id=r["parent_id"],
        title=r["title"], url_slug=r["url_slug"], full_url=r["full_url"],
    )


def _poem_from_row(r: sqlite3.Row) -> Poem:
    return Poem(
        id=r["id"], cat_id=r["cat_id"], poet_id=r["poet_id"],
        title=r["title"], url_slug=r["url_slug"], full_url=r["full_url"],
    )


def _verse_from_row(r: sqlite3.Row) -> Verse:
    return Verse(
        id=r["id"], poem_id=r["poem_id"], v_order=r["v_order"],
        verse_position=r["verse_position"], text=r["text"],
    )


# ---------------------------------------------------------------------------
# Path / link helpers
# ---------------------------------------------------------------------------

def _cat_link(cat: Category, poet: Poet) -> str:
    relative = cat.full_url[len(poet.full_url):].lstrip("/")
    if relative:
        return f"poets/{poet.slug}/{relative}/_index"
    return f"poets/{poet.slug}/_index"


def _poem_link(poem: Poem, poet: Poet) -> str:
    relative = poem.full_url[len(poet.full_url):].lstrip("/")
    return f"poets/{poet.slug}/{relative}" if relative else f"poets/{poet.slug}/{poem.url_slug or poem.id}"


def _cats_ctx(cats: list[Category], poet: Poet) -> list[dict]:
    return [{"title": c.title, "link": _cat_link(c, poet)} for c in cats]


def _poems_ctx(poems: list[Poem], poet: Poet) -> list[dict]:
    return [{"title": p.title, "link": _poem_link(p, poet)} for p in poems]


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------

def _write(path: Path, content: str, force: bool) -> tuple[int, int]:
    if path.exists() and not force:
        return 0, 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return 1, 0


# ---------------------------------------------------------------------------
# Per-poet export (uses its own DB connection — safe to call from any thread)
# ---------------------------------------------------------------------------

def _export_poet(
    conn: sqlite3.Connection,
    env: Environment,
    poet: Poet,
    vault: Path,
    force: bool,
) -> tuple[int, int]:
    written = skipped = 0

    cat_rows = conn.execute(
        "SELECT * FROM categories WHERE poet_id = ?", (poet.id,)
    ).fetchall()
    cats = {r["id"]: _cat_from_row(r) for r in cat_rows}

    children_of: dict[int | None, list[int]] = defaultdict(list)
    for cat in cats.values():
        children_of[cat.parent_id].append(cat.id)

    root_id = poet.root_cat_id
    if root_id is None or root_id not in cats:
        return 0, 0

    poet_dir = vault / "poets" / poet.slug
    poet_dir.mkdir(parents=True, exist_ok=True)

    top_cats = [cats[cid] for cid in children_of.get(root_id, []) if cid in cats]
    era = classify_era(poet.birth_year_in_lh)
    w, s = _write(
        poet_dir / "_index.md",
        env.get_template("poet_index.md.j2").render(
            poet=poet, era=era, categories=_cats_ctx(top_cats, poet)
        ),
        force,
    )
    written += w; skipped += s

    stack = list(children_of.get(root_id, []))
    while stack:
        cat_id = stack.pop()
        if cat_id not in cats:
            continue
        cat = cats[cat_id]

        relative = cat.full_url[len(poet.full_url):].lstrip("/")
        cat_dir = (vault / "poets" / poet.slug / relative) if relative else poet_dir
        cat_dir.mkdir(parents=True, exist_ok=True)

        sub_cat_ids = children_of.get(cat_id, [])
        sub_cats = [cats[cid] for cid in sub_cat_ids if cid in cats]

        poem_rows = conn.execute(
            "SELECT * FROM poems WHERE cat_id = ? AND fetched_at IS NOT NULL", (cat_id,)
        ).fetchall()
        poems = [_poem_from_row(r) for r in poem_rows]

        w, s = _write(
            cat_dir / "_index.md",
            env.get_template("book_index.md.j2").render(
                cat=cat,
                sub_categories=_cats_ctx(sub_cats, poet),
                poems=_poems_ctx(poems, poet),
            ),
            force,
        )
        written += w; skipped += s

        for poem in poems:
            verse_rows = conn.execute(
                "SELECT * FROM verses WHERE poem_id = ? ORDER BY v_order", (poem.id,)
            ).fetchall()
            verses = [_verse_from_row(r) for r in verse_rows]
            rendered = render_verses(verses)

            poem_relative = poem.full_url[len(poet.full_url):].lstrip("/")
            if not poem_relative:
                poem_relative = poem.url_slug or str(poem.id)
            poem_path = vault / "poets" / poet.slug / (poem_relative + ".md")

            w, s = _write(
                poem_path,
                env.get_template("poem.md.j2").render(
                    poem=poem,
                    poet=poet,
                    era=era,
                    poet_tag=poet.slug,
                    rendered_verses=rendered,
                ),
                force,
            )
            written += w; skipped += s

        stack.extend(sub_cat_ids)

    return written, skipped


def _export_poet_worker(
    db_path: str,
    env: Environment,
    poet: Poet,
    vault: Path,
    force: bool,
) -> tuple[int, int]:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return _export_poet(conn, env, poet, vault, force)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def export_vault(
    db_path: str,
    vault_path: str,
    poet_filter: str | None = None,
    force: bool = False,
) -> None:
    vault = Path(vault_path)
    vault.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        if poet_filter:
            slug = poet_filter.lstrip("/")
            rows = conn.execute(
                "SELECT * FROM poets WHERE full_url = ? AND fetched_at IS NOT NULL",
                ("/" + slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM poets WHERE fetched_at IS NOT NULL ORDER BY name"
            ).fetchall()

        poets = [_poet_from_row(r) for r in rows]

    total_written = total_skipped = 0

    workers = 1 if poet_filter else _WORKERS
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_export_poet_worker, db_path, env, poet, vault, force): poet
            for poet in poets
        }
        with tqdm(total=len(poets), desc="  Poets", unit="poet") as pbar:
            for future in as_completed(futures):
                try:
                    w, s = future.result()
                    total_written += w
                    total_skipped += s
                except Exception as exc:
                    poet = futures[future]
                    tqdm.write(f"Warning: export failed for {poet.slug}: {exc}", file=sys.stderr)
                finally:
                    pbar.update(1)

    # vault/_index.md — written in main thread after all poets complete
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM poets WHERE fetched_at IS NOT NULL ORDER BY name"
        ).fetchall()
        all_poets = [_poet_from_row(r) for r in rows]

    poets_by_era: dict[str, list] = defaultdict(list)
    for poet in all_poets:
        era = classify_era(poet.birth_year_in_lh)
        poets_by_era[era].append({"name": poet.name, "slug": poet.slug})

    ordered = {era: poets_by_era[era] for era in _ERA_ORDER if era in poets_by_era}
    w, s = _write(
        vault / "_index.md",
        env.get_template("vault_index.md.j2").render(poets_by_era=ordered),
        force,
    )
    total_written += w; total_skipped += s

    print(f"Export complete: {total_written} written, {total_skipped} skipped")
