"""Turn an OpenSourcePOS item export into Sukoon's product import file (ADR-0043 §1).

    python scripts/prepare_product_import.py SOURCE.csv OUT.csv [--categories MAPPING.csv]

Run once by the developer, not by the shop. It only cleans; it does not decide. Duplicates
and paisa are kept as found — the owner decides those on Sukoon's review screen. What it does:

* drops the barcode column entirely: Excel destroyed most of them (``8.96E+12``), and a wrong
  barcode sells the wrong product;
* trims and collapses spaces;
* drops rows that are not products (blank name, a number for a name, ``test``) and says which;
* blanks a cost or price of a million rupees or more (a barcode in the wrong column) and a
  cost of zero (unknown, never zero — ADR-0011);
* renames categories from MAPPING.csv's ``correct_category`` column where it is filled in.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

OUT_COLUMNS = ["Name", "Category", "Cost Price", "Selling Price", "Low Stock Level"]

_SPACES = re.compile(r"\s+")
_NUMBER_NAME = re.compile(r"[\d.,Ee+\-]+")
_ABSURD = Decimal(1_000_000)
_JUNK_NAMES = {"test"}


def tidy(text: str | None) -> str:
    return _SPACES.sub(" ", (text or "").strip())


def _amount(raw: str | None, *, zero_is_unknown: bool) -> str:
    """A cleaned amount as text, or ``""`` for unknown. Keeps paisa: rounding is Sukoon's job."""
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        value = Decimal(text)
    except InvalidOperation:
        return ""
    if value < 0 or value >= _ABSURD or (zero_is_unknown and value == 0):
        return ""
    return format(value.normalize(), "f")


def _level(raw: str | None) -> str:
    try:
        value = int(Decimal((raw or "").strip()))
    except (InvalidOperation, ValueError):
        return ""
    return str(value) if value >= 0 else ""


@dataclass
class Prepared:
    rows: list[dict] = field(default_factory=list)
    dropped: list[tuple[int, str, str]] = field(default_factory=list)  # (line, name, why)


def load_category_map(path: str | None) -> dict[str, str]:
    """``category_in_file`` (case-insensitive) -> ``correct_category``, filled-in rows only."""
    if not path:
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {
            tidy(r["category_in_file"]).lower(): tidy(r["correct_category"])
            for r in csv.DictReader(f)
            if tidy(r.get("correct_category"))
        }


def prepare(source_rows, category_map: dict[str, str] | None = None) -> Prepared:
    category_map = category_map or {}
    out = Prepared()
    for line, r in enumerate(source_rows, start=2):  # line 1 is the header
        name = tidy(r.get("Item Name"))
        if not name:
            out.dropped.append((line, name, "no name"))
            continue
        if name.lower() in _JUNK_NAMES:
            out.dropped.append((line, name, "a test row"))
            continue
        if _NUMBER_NAME.fullmatch(name):
            out.dropped.append((line, name, "the name is a number, not a product"))
            continue
        category = tidy(r.get("Category"))
        if category.lower() in ("", "(blank)"):
            category = ""
        category = category_map.get(category.lower(), category)
        out.rows.append({
            "Name": name,
            "Category": category,
            "Cost Price": _amount(r.get("Cost Price"), zero_is_unknown=True),
            "Selling Price": _amount(r.get("Unit Price"), zero_is_unknown=True),
            "Low Stock Level": _level(r.get("Reorder Level")),
        })
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source")
    parser.add_argument("out")
    parser.add_argument("--categories", help="category-mapping.csv with correct_category filled")
    args = parser.parse_args(argv)

    with open(args.source, encoding="utf-8-sig", errors="replace", newline="") as f:
        result = prepare(csv.DictReader(f), load_category_map(args.categories))
    # utf-8-sig so Excel shows Urdu or accented names correctly if the file is opened there
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(result.rows)

    print(f"{len(result.rows)} products written to {args.out}")
    for line, name, why in result.dropped:
        print(f"  dropped line {line}: {name!r} — {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
