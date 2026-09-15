"""The shop's clock (ADR-0024) — pure conversion, no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sukoon.services.clock import convert


def test_naive_and_aware_utc_both_convert_to_pakistan_time():
    naive = datetime(2026, 9, 14, 13, 54)  # SQLite hands timestamps back naive
    aware = datetime(2026, 9, 14, 13, 54, tzinfo=UTC)
    for dt in (naive, aware):
        local = convert(dt, "Asia/Karachi")
        assert (local.hour, local.minute) == (18, 54)
        assert local.utcoffset() == timedelta(hours=5)


def test_an_unknown_zone_falls_back_instead_of_raising():
    local = convert(datetime(2026, 9, 14, 13, 54, tzinfo=UTC), "Mars/Olympus_Mons")
    assert local.utcoffset() == timedelta(hours=5)


def test_new_year_arrives_at_the_shops_midnight():
    local = convert(datetime(2026, 12, 31, 20, 0, tzinfo=UTC), "Asia/Karachi")
    assert (local.year, local.month, local.day, local.hour) == (2027, 1, 1, 1)


def test_the_shop_clock_has_no_leading_zero(monkeypatch):
    from sukoon.services import clock

    monkeypatch.setattr(clock, "shop_zone_name", lambda: "Asia/Karachi")
    assert clock.format_clock(datetime(2026, 9, 15, 16, 56, tzinfo=UTC)) == "9:56 PM"
    assert clock.format_clock(datetime(2026, 9, 15, 7, 5, tzinfo=UTC)) == "12:05 PM"
    assert clock.format_clock(datetime(2026, 9, 14, 19, 30, tzinfo=UTC)) == "12:30 AM"
    assert (
        clock.format_clock(datetime(2026, 8, 5, 15, 26, tzinfo=UTC), with_date=True)
        == "5 Aug, 8:26 PM"
    )
