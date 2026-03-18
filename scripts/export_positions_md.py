#!/usr/bin/env python3
"""docs/ПОЗИЦИИ_И_ПОЧТЫ.md из vendors.json (лист «Бренды»)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDORS = ROOT / "em_portfolio_bot" / "vendors.json"
OUT = ROOT / "docs" / "ПОЗИЦИИ_И_ПОЧТЫ.md"


def main() -> None:
    data = json.loads(VENDORS.read_text(encoding="utf-8"))
    data.sort(
        key=lambda x: (
            (x.get("direction") or "").lower(),
            (x.get("group") or "").lower(),
            (x.get("brand") or "").lower(),
        )
    )
    lines = [
        "# Бренд → почта (лист «Бренды»)",
        "",
        "| Направление | Группа | Бренд | E-mail |",
        "|-------------|--------|-------|--------|",
    ]
    for e in data:
        d = str(e.get("direction") or "—").replace("|", "\\|")
        g = str(e.get("group") or "—").replace("|", "\\|")
        b = str(e.get("brand") or "").replace("|", "\\|")
        em = str(e.get("email") or "").replace("|", "\\|")
        lines.append(f"| {d} | {g} | {b} | {em} |")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: {len(data)} строк → {OUT}")


if __name__ == "__main__":
    main()
