from dataclasses import dataclass


@dataclass
class Poet:
    id: int
    name: str
    full_url: str          # e.g. "/azar"
    nickname: str | None
    description: str | None
    birth_year_in_lh: int | None
    death_year_in_lh: int | None
    root_cat_id: int | None

    @property
    def slug(self) -> str:
        return self.full_url.lstrip("/")


@dataclass
class Category:
    id: int
    poet_id: int
    parent_id: int | None
    title: str
    url_slug: str
    full_url: str


@dataclass
class Poem:
    id: int
    cat_id: int
    poet_id: int
    title: str
    url_slug: str | None
    full_url: str          # e.g. "/azar/divan/tarjee"

    @property
    def source_url(self) -> str:
        return f"https://ganjoor.net{self.full_url}"


@dataclass
class Verse:
    id: int
    poem_id: int
    v_order: int
    verse_position: int    # 0=right hemistich, 1=left, 2=single line, 3=prose
    text: str
