"""Sending ESC/POS bytes to the shop's thermal printer (Development Spec Phase 3).

The printer is configured through the ``setting`` table, not code — a shop swaps
printers without a redeploy (and Phase 7 does the per-model testing). Anything
going wrong here raises ``PrinterUnavailable``; the caller
(``receipts.issue_receipt``) turns that into a PDF, so a dead printer never
blocks a sale (ADR-0003 §6, Development Spec §11 Phase 3 required test).

No Flask import (ADR-0003 §1).
"""
from __future__ import annotations

import logging

from sukoon.services import settings_service

log = logging.getLogger(__name__)

# setting keys
_KIND = "receipt.printer.kind"  # 'none' | 'network' | 'usb' | 'serial' | 'file'
_HOST = "receipt.printer.host"
_PORT = "receipt.printer.port"
_TIMEOUT = "receipt.printer.timeout_seconds"
_USB_VENDOR = "receipt.printer.usb_vendor_id"
_USB_PRODUCT = "receipt.printer.usb_product_id"
_SERIAL_DEV = "receipt.printer.serial_device"
_FILE_DEV = "receipt.printer.device_file"  # e.g. /dev/usb/lp0 on Linux


class PrinterUnavailable(Exception):
    """No printer is configured, or it could not be reached."""


def printer_kind() -> str:
    return (settings_service.get(_KIND, "none") or "none").strip().lower()


def _build_printer():
    kind = printer_kind()
    timeout = _get_float(_TIMEOUT, 5.0)

    if kind == "none":
        raise PrinterUnavailable("No receipt printer is configured.")

    # Imported lazily: the USB/serial backends pull in system libraries that a
    # network-only or PDF-only install does not have.
    if kind == "network":
        from escpos.printer import Network

        host = settings_service.get(_HOST)
        if not host:
            raise PrinterUnavailable("The network printer has no address set.")
        return Network(
            host, port=settings_service.get_int(_PORT, 9100), timeout=timeout
        )

    if kind == "usb":
        from escpos.printer import Usb

        vendor = settings_service.get_int(_USB_VENDOR, 0)
        product = settings_service.get_int(_USB_PRODUCT, 0)
        if not vendor or not product:
            raise PrinterUnavailable("The USB printer's vendor/product id is not set.")
        return Usb(vendor, product)

    if kind == "serial":
        from escpos.printer import Serial

        dev = settings_service.get(_SERIAL_DEV)
        if not dev:
            raise PrinterUnavailable("The serial printer's device is not set.")
        return Serial(devfile=dev, timeout=timeout)

    if kind == "file":
        # A printer exposed as a character device the OS already drives
        # (Linux: /dev/usb/lp0). Also the seam the receipt tests write through.
        from escpos.printer import File

        dev = settings_service.get(_FILE_DEV)
        if not dev:
            raise PrinterUnavailable("The printer's device file is not set.")
        return File(devfile=dev, auto_flush=True)

    raise PrinterUnavailable(f"Unknown printer kind: {kind!r}")


def send(data: bytes) -> None:
    """Push raw ESC/POS bytes to the configured printer. Raises
    ``PrinterUnavailable`` for every failure mode — no printer, bad address,
    connection refused, missing USB backend, a timeout."""
    try:
        device = _build_printer()
    except PrinterUnavailable:
        raise
    except Exception as exc:  # a backend import or construction failure
        raise PrinterUnavailable(str(exc)) from exc

    try:
        device._raw(data)
    except Exception as exc:  # connection refused, timeout, write error
        raise PrinterUnavailable(str(exc)) from exc
    finally:
        try:
            device.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass


def _get_float(key: str, default: float) -> float:
    raw = settings_service.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default
