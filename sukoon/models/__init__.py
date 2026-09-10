"""SQLAlchemy models — shape and constraints only (ADR-0003).

Every table in ADR-0016 has a model here. Importing this package registers all
tables on ``db.metadata`` for Alembic autogenerate and for the test database's
``create_all()``.
"""
from __future__ import annotations

from sukoon.models.catalog import Category, Product, ProductBarcode
from sukoon.models.customer import PHONE_VERIFIED_METHODS, Customer
from sukoon.models.inventory import MOVEMENT_TYPES, StockMovement
from sukoon.models.khata import LEDGER_ENTRY_TYPES, CreditLedgerEntry
from sukoon.models.notifications import (
    NOTIFICATION_STATUSES,
    NOTIFICATION_TYPES,
    NotificationQueue,
)
from sukoon.models.sales import (
    PAYMENT_METHODS,
    QUANTITY_SOURCES,
    SALE_STATUSES,
    Payment,
    Sale,
    SaleItem,
)
from sukoon.models.system import InvoiceCounter, Setting
from sukoon.models.user import (
    ROLE_ADMIN,
    ROLE_CASHIER,
    ROLES,
    Permission,
    RolePermission,
    User,
)

__all__ = [
    "Category",
    "Product",
    "ProductBarcode",
    "Customer",
    "PHONE_VERIFIED_METHODS",
    "StockMovement",
    "MOVEMENT_TYPES",
    "CreditLedgerEntry",
    "LEDGER_ENTRY_TYPES",
    "NotificationQueue",
    "NOTIFICATION_TYPES",
    "NOTIFICATION_STATUSES",
    "Sale",
    "SaleItem",
    "Payment",
    "PAYMENT_METHODS",
    "SALE_STATUSES",
    "QUANTITY_SOURCES",
    "InvoiceCounter",
    "Setting",
    "User",
    "Permission",
    "RolePermission",
    "ROLE_ADMIN",
    "ROLE_CASHIER",
    "ROLES",
]
