_ERA_BANDS = [
    (300, "early-islamic"),
    (500, "khorasani"),
    (700, "seljuk"),
    (900, "ilkhanid-timurid"),
    (1100, "safavid"),
    (1300, "qajar"),
]


def classify_era(birth_year_in_lh: int | None) -> str:
    if birth_year_in_lh is None:
        return "unknown-era"
    for threshold, label in _ERA_BANDS:
        if birth_year_in_lh < threshold:
            return label
    return "modern"
