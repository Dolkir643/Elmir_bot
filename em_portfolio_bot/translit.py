# -*- coding: utf-8 -*-
"""Транслитерация кириллица ↔ латиница для поиска брендов."""

# Кириллица → латиница: сначала диграфы, потом одиночные
CYR_DIGRAPHS = [
    ("щ", "shch"), ("ш", "sh"), ("ч", "ch"), ("ж", "zh"), ("х", "kh"),
    ("ю", "yu"), ("я", "ya"), ("ё", "e"), ("й", "y"),
]
_CYR_SINGLE = "абвгдезиклмнопрстуфцыэ"
_LAT_SINGLE = "abvgdeziklmnoprstufcye"
CYR_TO_LAT = str.maketrans(_CYR_SINGLE + _CYR_SINGLE.upper(), _LAT_SINGLE + _LAT_SINGLE.upper())

# Латиница → кириллица (длинные сочетания первыми)
LAT_TO_CYR = [
    ("shch", "щ"), ("sch", "шч"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"),
    ("yu", "ю"), ("ya", "я"), ("ts", "ц"), ("sh", "ш"),
]
_LAT = "abvgdeziyklmnoprstufcye"
_CYR = "абвгдезийклмнопрстуфцыэ"
LAT_SINGLE = str.maketrans(_LAT + _LAT.upper(), _CYR + _CYR.upper())
LAT_SINGLE2 = str.maketrans("eotEOT", "еотЕОТ")


def cyr_to_lat(text: str) -> str:
    """Приводит кириллицу к латинице для сравнения с брендами."""
    if not text:
        return text
    s = text.lower().strip()
    for cyr, lat in CYR_DIGRAPHS:
        s = s.replace(cyr, lat)
    s = s.translate(CYR_TO_LAT)
    return s


def lat_to_cyr(text: str) -> str:
    """Приводит латиницу к кириллице (как слышится)."""
    if not text:
        return text
    s = text.lower().strip()
    for lat, cyr in LAT_TO_CYR:
        s = s.replace(lat, cyr)
    s = s.translate(LAT_SINGLE)
    s = s.translate(LAT_SINGLE2)
    return s


def has_cyrillic(s: str) -> bool:
    return any("\u0400" <= c <= "\u04FF" for c in (s or ""))


def query_variants(query: str) -> list[str]:
    """Все варианты запроса для поиска: нормализованный + транслит."""
    q = (query or "").strip().lower()
    out = [q]
    if has_cyrillic(q):
        out.append(cyr_to_lat(q))
    else:
        out.append(lat_to_cyr(q))
    return [x for x in out if x and len(x) >= 2]
