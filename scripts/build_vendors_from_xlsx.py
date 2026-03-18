#!/usr/bin/env python3
"""
Собирает vendors.json из листа «Бренды» в «Портфель ЭМ для партнеров.xlsx».
Структура листа: направление → (группы) → строки бренд | почта.
Только стандартная библиотека.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Заголовки направлений (строка с почтой в кол. B или предыдущая строка без почты)
DIRECTIONS = frozenset({
    "Сервера и СХД",
    "Голос и коммуникация",
    "Информационная безопасность",
    "Печать и МФУ",
    "Сетевые решения",
    "IT- инженерные системы",
    "ПК и мобильные устройства",
    "AV и ВКС",
})

# Группы внутри направления (строка «название группы | та же почта»)
GROUPS = frozenset({
    "Коммутаторы",
    "Маршрутизаторы",
    "Wi-Fi",
    "Системы управления и мониторинга",
    "БРП",
    "ИБП",
    "СКС",
    "Стойки и шкафы",
    "Холод",
    "Ноутбуки",
    "ПК (вкл. моно, мини)",
    "АРМ",
    "Планшеты, смартфоны",
    "Мониторы",
    "Аксессуары",
    "ВКС и конгресс-системы",
    "Системы отображения",
    "Автоматизация и управления AV-систем",
    "Световое оборудование и управление",
    "Проекционное оборудование",
    "Аудио",
})


def col_row(ref: str) -> tuple[int, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref)
    if not m:
        return 0, 0
    c = 0
    for ch in m.group(1):
        c = c * 26 + (ord(ch) - 64)
    return c, int(m.group(2))


def is_email(s: str) -> bool:
    s = (s or "").strip()
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", s))


def load_sheet2_cells(path: str) -> dict[tuple[int, int], str]:
    z = zipfile.ZipFile(path)
    ss: list[str] = []
    with z.open("xl/sharedStrings.xml") as f:
        root = ET.parse(f).getroot()
        for si in root.findall(".//m:si", NS):
            ss.append("".join(t.text or "" for t in si.findall(".//m:t", NS)))

    cells: dict[tuple[int, int], str] = {}
    with z.open("xl/worksheets/sheet2.xml") as f:
        root = ET.parse(f).getroot()
        for c in root.findall(".//m:c", NS):
            ref = c.get("r")
            if not ref:
                continue
            col, row = col_row(ref)
            t, v = c.get("t"), c.find("m:v", NS)
            is_node = c.find("m:is", NS)
            if is_node is not None:
                t_el = is_node.find(".//m:t", NS)
                val = t_el.text if t_el is not None else ""
            elif v is not None and v.text is not None:
                val = ss[int(v.text)] if t == "s" else v.text
            else:
                continue
            cells[(row, col)] = str(val).strip()
    return cells


def parse_brands_sheet(cells: dict[tuple[int, int], str]) -> list[dict]:
    max_r = max((r for r, _ in cells), default=0)
    direction = ""
    group = ""
    out: list[dict] = []

    for r in range(1, max_r + 1):
        a = cells.get((r, 1), "").strip()
        b = cells.get((r, 2), "").strip()
        if not a and not b:
            continue

        # Только заголовок направления в A, почты в B нет (блок «Голос»)
        if a and not b and not is_email(a):
            direction = a
            group = ""
            continue

        # Строка «voice@…» только в A
        if is_email(a) and not b:
            continue

        if not is_email(b):
            continue

        email = b
        label = a

        if label in DIRECTIONS:
            direction = label
            group = ""
            continue
        if label in GROUPS:
            group = label
            continue

        out.append(
            {
                "brand": label,
                "email": email,
                "direction": direction,
                "group": group,
            }
        )

    return out


def main() -> None:
    xlsx = sys.argv[1] if len(sys.argv) > 1 else "Портфель ЭМ для партнеров.xlsx"
    out = sys.argv[2] if len(sys.argv) > 2 else "em_portfolio_bot/vendors.json"

    cells = load_sheet2_cells(xlsx)
    rows = parse_brands_sheet(cells)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"Лист «Бренды»: {len(rows)} строк брендов → {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
