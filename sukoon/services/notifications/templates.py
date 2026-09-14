"""The approved WhatsApp wording (ADR-0030, ADR-0032) — pure.

Each message type maps to a Meta template name and an ordered list of values. The same
function renders the exact text a customer reads, so tests (and the fake provider)
assert real wording. Changing a sentence here without Meta re-approving it breaks
sending — and ADR-0030 §7 says wording changes come back for sign-off first.
"""
from __future__ import annotations

from dataclasses import dataclass

SHOP = "Al-Rehman General Store"  # fixed inside the approved templates (ADR-0030)
LANGUAGE = "en"
TEMPLATE_NAMES = {
    "credit_sale": "sukoon_credit_sale",
    "payment_receipt": "sukoon_payment_receipt",
    "account_notice": "sukoon_account_notice",
    "statement": "sukoon_statement",
    "overdue_reminder": "sukoon_overdue_reminder",
    "test": "sukoon_account_notice",  # ADR-0033 §10: a test sends the account notice
}
_NO_REPLIES = "This number can't read replies."
_ASK = "For questions, contact the shop on {reply_to}."


@dataclass(frozen=True)
class Rendered:
    template: str
    params: list[str]
    text: str
    document_name: str | None = None


def items_phrase(count: int) -> str:
    return f"{count} item" if count == 1 else f"{count} items"


def render(notification_type: str, payload: dict, *, reply_to: str) -> Rendered:
    p = payload
    t = notification_type
    if t == "credit_sale":
        params = [p["items"], p["amount"], p["as_of"], p["previous"], p["new"], reply_to]
        text = (f"{SHOP}: {p['items']}, {p['amount']}, added to your Khata as of {p['as_of']}. "
                f"Previous balance: {p['previous']}. New balance: {p['new']}. "
                f"{_NO_REPLIES} {_ASK.format(reply_to=reply_to)}")
    elif t == "payment_receipt":
        params = [p["amount"], p["as_of"], p["new"], reply_to]
        text = (f"{SHOP}: payment of {p['amount']} received on your Khata as of {p['as_of']}. "
                f"New balance: {p['new']}. {_NO_REPLIES} {_ASK.format(reply_to=reply_to)}")
    elif t in ("account_notice", "test"):
        params = [p["name"], reply_to]
        text = (f"An account has been opened in the name of {p['name']} at {SHOP}. "
                f"If this is not you, please contact the shop on {reply_to}. {_NO_REPLIES}")
    elif t == "statement":
        params = [p["month"], p["closing"], reply_to]
        text = (f"Your Khata statement for {p['month']} from {SHOP} is attached. "
                f"Closing balance: {p['closing']}. {_NO_REPLIES} {_ASK.format(reply_to=reply_to)}")
        return Rendered(TEMPLATE_NAMES[t], params, text,
                        document_name=f"Khata statement {p['month']}.pdf")
    elif t == "overdue_reminder":
        params = [p["balance"], p["as_of"], reply_to]
        text = (f"A gentle reminder from {SHOP}: {p['balance']} is due on your Khata, as of "
                f"{p['as_of']}. If you have already paid, thank you, and please ignore this "
                f"message. {_NO_REPLIES} {_ASK.format(reply_to=reply_to)}")
    else:
        raise ValueError(f"No template for message type {t!r}")
    return Rendered(TEMPLATE_NAMES[t], params, text)
