"""Reading a product spreadsheet (ADR-0043): the developer's prepare script and the importer's
own parsing. No database."""
from __future__ import annotations

import pytest

from scripts.prepare_product_import import prepare
from sukoon.services.catalog_import_service import (
    ImportFileError,
    compute_initial_statuses,
    compute_price_paisa,
    compute_threshold_milli,
    decode_upload,
    parse_rows,
)

# --- the prepare script (§1) ------------------------------------------------------------

def _ospos(name, cat="Food", cost="10", price="12", level="1", barcode="8.96E+12"):
    return {"Barcode": barcode, "Item Name": name, "Category": cat, "Cost Price": cost,
            "Unit Price": price, "Reorder Level": level}


def test_prepare_drops_the_barcodes_and_writes_sukoons_columns():
    out = prepare([_ospos("  Sufi   Oil 1L ", " Oil ", "509.4", "520", "2")])
    assert out.rows == [{"Name": "Sufi Oil 1L", "Category": "Oil", "Cost Price": "509.4",
                         "Selling Price": "520", "Low Stock Level": "2"}]
    assert "Barcode" not in out.rows[0]


def test_prepare_drops_rows_that_are_not_products_and_says_why():
    out = prepare([_ospos("test"), _ospos("7.70E+11"), _ospos("   "), _ospos("Real")])
    assert [r["Name"] for r in out.rows] == ["Real"]
    assert [why for _, _, why in out.dropped] == [
        "a test row", "the name is a number, not a product", "no name"]


@pytest.mark.parametrize("cost, price, want_cost, want_price", [
    ("8.96E+12", "0", "", ""),        # a barcode in the cost column; no price
    ("0", "120", "", "120"),          # zero cost is unknown, never zero
    ("4.3", "5", "4.3", "5"),         # paisa kept: the owner sees the rounding in Sukoon
    ("", "", "", ""),
])
def test_prepare_blanks_impossible_figures(cost, price, want_cost, want_price):
    row = prepare([_ospos("X", cost=cost, price=price)]).rows[0]
    assert (row["Cost Price"], row["Selling Price"]) == (want_cost, want_price)


def test_prepare_keeps_duplicates_for_the_owner_to_decide():
    assert len(prepare([_ospos("Ghee"), _ospos("Ghee", price="13")]).rows) == 2


def test_prepare_renames_categories_from_the_mapping():
    out = prepare([_ospos("A", cat="Shamapoo"), _ospos("B", cat="Soap")],
                  {"shamapoo": "Shampoo"})
    assert [r["Category"] for r in out.rows] == ["Shampoo", "Soap"]


# --- money and quantities (§3) ------------------------------------------------------------

@pytest.mark.parametrize("raw, paisa", [
    ("4.3", 430), ("4.5", 450), ("1594.23", 159423), ("1594.235", 159424), ("1,050", 105000),
    ("30", 3000), ("0.3", 30),
    ("0", None), ("", None), ("abc", None), ("-5", None),
    ("8.96E+12", None), ("1000000", None), ("999999", 99999900),
])
def test_money_keeps_its_paisa_or_is_unknown(raw, paisa):
    """ADR-0044: paisa is kept exactly; only a third decimal rounds, half-up, to the paisa."""
    assert compute_price_paisa(raw) == paisa


@pytest.mark.parametrize("raw, milli", [("1", 1000), ("0", 0), ("", None), ("x", None),
                                        ("-1", None), ("3.0", 3000)])
def test_low_stock_level_is_whole_units(raw, milli):
    assert compute_threshold_milli(raw) == milli


def test_an_excel_file_with_a_byte_order_mark_or_old_encoding_still_reads():
    assert decode_upload("﻿Name".encode()) == "Name"
    assert decode_upload("Caf\xe9".encode("cp1252")) == "Café"


# --- the file ---------------------------------------------------------------------------

def test_headers_are_matched_ignoring_case_spaces_and_order():
    rows = parse_rows("selling  price, NAME ,Cost Price\n120,Ghee 1kg,99.5\n\n")
    assert len(rows) == 1
    r = rows[0]
    assert (r.name, r.sell_price_paisa, r.cost_price_paisa, r.source_cost, r.category) == (
        "Ghee 1kg", 12000, 9950, "99.5", None)


@pytest.mark.parametrize("text, words", [
    ("", "empty"),
    ("Name,Category\nGhee,Food\n", "Selling Price"),
    ("Name,Selling Price\n", "no products"),
])
def test_a_file_that_is_not_a_product_list_is_refused_plainly(text, words):
    with pytest.raises(ImportFileError, match=words):
        parse_rows(text)


# --- duplicates (§2) ---------------------------------------------------------------------

def _statuses(csv_text):
    return compute_initial_statuses(parse_rows("Name,Category,Cost Price,Selling Price\n"
                                               + csv_text))


def test_identical_copies_collapse_onto_the_first():
    assert _statuses("Ghee,Food,10,12\n ghee ,food,10.00,12\nGHEE,Food,10.20,12\n") == [
        ("choose", None), ("choose", None), ("choose", None)]  # Rs 10.20 is not Rs 10
    assert _statuses("Ghee,Food,10,12\n ghee ,food,10.00,12\n") == [
        ("ready", None), ("skipped", "Same as line 2")]


def test_copies_that_differ_wait_for_the_owner():
    assert _statuses("Ghee,Food,10,12\nGhee,Food,10,13\nOil,Food,1,2\n") == [
        ("choose", None), ("choose", None), ("ready", None)]


def test_a_row_without_a_price_needs_one_and_a_row_without_a_name_is_skipped():
    assert _statuses("Ghee,Food,10,\n,Food,1,2\n") == [
        ("needs_price", None), ("skipped", "No name")]
