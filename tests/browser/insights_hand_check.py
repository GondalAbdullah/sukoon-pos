"""An independent check of the Insights arithmetic.

Numbers worked out by hand below, then compared with what Sukoon reports. Deliberately does not
reuse the reporting tests' scenario: a test written beside the code can share the code's mistake.

The shop:
  Cooking Oil  sells Rs 590, costs Rs 500
  Ghee         sells Rs 600, costs Rs 520
  Soap         sells Rs 280, costs Rs 200
  Toffee       sells Rs  50, cost unknown

Today:
  sale 1  2 x Oil                    Rs 1,180  cash
  sale 2  1 x Ghee + 1 x Soap        Rs   880  on Khata
  sale 3  3 x Toffee                 Rs   150  card
  refund  1 x Oil from sale 1        Rs   590  approved today, the item goes back on the shelf
"""
from datetime import UTC, datetime

from sukoon.app import create_app
from sukoon.extensions import db
from sukoon.models.user import User
from sukoon.seed import seed_invoice_counter, seed_permissions
from sukoon.services import inventory_service as inv
from sukoon.services import khata_service as khata
from sukoon.services import refund_service, sales_service
from sukoon.services import reporting_service as rpt
from sukoon.services.auth_service import hash_password
from sukoon.services.sales_service import CartLine

NOW = datetime.now(UTC)

app = create_app("testing")
with app.app_context():
    db.create_all()
    seed_permissions()
    seed_invoice_counter()
    admin = User(name="Owner", initials="OW", role="admin", password_hash=hash_password("x"))
    cashier = User(name="Till", initials="T1", role="cashier", password_hash=hash_password("x"))
    db.session.add_all([admin, cashier])
    db.session.commit()

    def product(name, sell, cost=None):
        p = inv.create_product(name=name, sell_price_paisa=sell, cost_price_paisa=cost)
        inv.apply_stock_movement(product=p, movement_type="stock_in", quantity_milli=50_000,
                                 reason="in", user_id=admin.id)
        return p

    oil = product("Cooking Oil", 59_000, 50_000)
    ghee = product("Ghee", 60_000, 52_000)
    soap = product("Soap", 28_000, 20_000)
    toffee = product("Toffee", 5_000, None)
    customer = khata.create_customer(name="Haji Usman", phone_raw="0300 5541298",
                                     user_id=cashier.id)

    def line(p, units):
        return CartLine(product=p, quantity_milli=units * 1000,
                        unit_price_paisa=p.sell_price_paisa, quantity_source="stepper")

    sale1 = sales_service.record_sale(lines=[line(oil, 2)], payment_method="cash",
                                      user_id=cashier.id, now=NOW)
    sales_service.record_sale(lines=[line(ghee, 1), line(soap, 1)], payment_method="credit",
                              customer_id=customer.id, user_id=cashier.id, now=NOW)
    sales_service.record_sale(lines=[line(toffee, 3)], payment_method="card",
                              user_id=cashier.id, now=NOW)

    item = sale1.items[0]
    pending = refund_service.initiate_refund(
        sale_id=sale1.id,
        lines=[refund_service.RefundLineSpec(sale_item_id=item.id, quantity_milli=1_000,
                                             restock=True)],
        reason="Customer changed their mind", initiated_by_user_id=cashier.id)
    refund_service.approve_refund(refund_id=pending.id, approved_by_user_id=admin.id)

    today = rpt.preset("today", now=NOW)
    totals = rpt.sales_totals(today)
    profit = rpt.estimated_profit(today)
    credit = rpt.outstanding_credit()

    # --- by hand -------------------------------------------------------------------------------
    gross = 1180 + 880 + 150
    refunds = 590
    net = gross - refunds                                    # 1,620
    # 1,470 — only lines whose product has a cost price
    covered = (1180 - 590) + 600 + 280
    uncovered = 150                                          # the toffee: cost unknown, left out
    # 1,220 — the restocked oil gives its cost back
    cost = (1000 - 500) + 520 + 200
    hand_profit = covered - cost                             # 250
    hand_margin = hand_profit / covered * 100                # 17.0%
    hand_coverage = covered / net * 100                      # 90.7%
    hand_credit = 880

    rows = [
        ("sales rung", 3, totals.count),
        ("gross sales", gross, totals.gross_paisa // 100),
        ("refunds", refunds, totals.refunds_paisa // 100),
        ("net sales", net, totals.net_paisa // 100),
        ("cash", 1180, totals.by_method.get("cash", 0) // 100),
        ("on Khata", 880, totals.by_method.get("credit", 0) // 100),
        ("card", 150, totals.by_method.get("card", 0) // 100),
        ("covered by known costs", covered, profit.covered_sales_paisa // 100),
        ("not covered", uncovered, profit.uncovered_sales_paisa // 100),
        ("estimated cost", cost, profit.estimated_cost_paisa // 100),
        ("estimated profit", hand_profit, profit.estimated_profit_paisa // 100),
        ("margin %", round(hand_margin, 1), round(profit.margin_percent, 1)),
        ("coverage %", round(hand_coverage, 1), round(profit.coverage_percent, 1)),
        ("credit outstanding", hand_credit, sum(c.balance_paisa for c in credit.owing) // 100),
    ]

    print(f"{'figure':28} {'by hand':>10} {'Sukoon':>10}   ")
    bad = 0
    for name, expected, actual in rows:
        ok = expected == actual
        bad += 0 if ok else 1
        print(f"{name:28} {expected:>10} {actual:>10}   {'ok' if ok else '<-- MISMATCH'}")
    print("\n" + ("every figure agrees" if not bad else f"{bad} figure(s) disagree"))
    db.drop_all()
