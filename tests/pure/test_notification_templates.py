"""The approved wording, character for character (ADR-0030 §6, ADR-0032 §5)."""
from __future__ import annotations

import pytest

from sukoon.services.notifications.templates import items_phrase, render

REPLY = "0300 1234567"


def test_credit_sale_matches_the_approved_wording():
    r = render("credit_sale", {"items": "4 items", "amount": "Rs 1,770",
                               "as_of": "14 Sep 2026, 8:26 PM", "previous": "Rs 8,260 owed",
                               "new": "Rs 10,030 owed"}, reply_to=REPLY)
    assert r.text == ("Al-Rehman General Store: 4 items, Rs 1,770, added to your Khata as of "
                      "14 Sep 2026, 8:26 PM. Previous balance: Rs 8,260 owed. New balance: "
                      "Rs 10,030 owed. This number can't read replies. For questions, contact "
                      "the shop on 0300 1234567.")
    assert r.template == "sukoon_credit_sale" and r.params[-1] == REPLY


def test_account_notice_matches_the_approved_wording():
    assert render("account_notice", {"name": "Haji Muhammad Usman"}, reply_to=REPLY).text == (
        "An account has been opened in the name of Haji Muhammad Usman at Al-Rehman General "
        "Store. If this is not you, please contact the shop on 0300 1234567. This number "
        "can't read replies.")


def test_statement_matches_and_carries_a_document():
    r = render("statement", {"month": "September 2026", "closing": "Rs 9,750 owed"},
               reply_to=REPLY)
    assert r.text == ("Your Khata statement for September 2026 from Al-Rehman General Store is "
                      "attached. Closing balance: Rs 9,750 owed. This number can't read replies. "
                      "For questions, contact the shop on 0300 1234567.")
    assert r.document_name == "Khata statement September 2026.pdf"


def test_overdue_reminder_matches_the_approved_wording():
    assert render("overdue_reminder", {"balance": "Rs 9,750", "as_of": "14 Sep 2026"},
                  reply_to=REPLY).text == (
        "A gentle reminder from Al-Rehman General Store: Rs 9,750 is due on your Khata, as of "
        "14 Sep 2026. If you have already paid, thank you, and please ignore this message. "
        "This number can't read replies. For questions, contact the shop on 0300 1234567.")


def test_payment_receipt_matches_the_approved_wording():
    assert render("payment_receipt", {"amount": "Rs 5,000", "as_of": "14 Sep 2026, 8:26 PM",
                                      "new": "Rs 250 in credit"}, reply_to=REPLY).text == (
        "Al-Rehman General Store: payment of Rs 5,000 received on your Khata as of "
        "14 Sep 2026, 8:26 PM. New balance: Rs 250 in credit. This number can't read replies. "
        "For questions, contact the shop on 0300 1234567.")


def test_no_message_contains_an_exclamation_mark_or_a_bare_negative():
    samples = [render(t, p, reply_to=REPLY).text for t, p in [
        ("credit_sale", {"items": "1 item", "amount": "Rs 5", "as_of": "x", "previous": "Settled",
                         "new": "Rs 5 owed"}),
        ("payment_receipt", {"amount": "Rs 5", "as_of": "x", "new": "Rs 5 in credit"}),
        ("account_notice", {"name": "A"}), ("statement", {"month": "m", "closing": "Settled"}),
        ("overdue_reminder", {"balance": "Rs 5", "as_of": "x"})]]
    assert all("!" not in s and "Rs -" not in s for s in samples)


def test_items_phrase_pluralises():
    assert (items_phrase(1), items_phrase(4)) == ("1 item", "4 items")


def test_an_unknown_type_has_no_template():
    with pytest.raises(ValueError):
        render("birthday_wishes", {}, reply_to=REPLY)
