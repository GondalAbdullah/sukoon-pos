"""Printing through Windows' own print system (ADR-0039 §1).

The shop's printer is a **USB** thermal printer. Talking to it directly over USB on Windows means
replacing the manufacturer's driver with a generic one, which breaks the manufacturer's own tools
and is unpleasant to support over the phone. Instead Sukoon hands the same ESC/POS bytes to the
printer as Windows already knows it — the "RAW" data type, which the spooler passes through
untouched.

Reached through ``ctypes``, like the DPAPI key store (ADR-0033): no pywin32 to bundle.

**Untested against real hardware** — the shop's printer model is O-25. Every failure raises
``PrinterUnavailable``, so a sale still completes and falls back to a PDF receipt (ADR-0003).
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_LEVEL = 4                      # PRINTER_INFO_4W: name, server, attributes
_ENUM_LOCAL = 0x00000002
_ENUM_CONNECTIONS = 0x00000004


class WindowsPrintError(RuntimeError):
    """Windows refused the print job. The message carries its error code."""


def available() -> bool:
    return sys.platform == "win32"


def _winspool():
    if not available():
        raise WindowsPrintError("Printing through Windows only works on Windows.")
    return ctypes.WinDLL("winspool.drv")


class _PrinterInfo4(ctypes.Structure):
    _fields_ = [("pPrinterName", wintypes.LPWSTR),
                ("pServerName", wintypes.LPWSTR),
                ("Attributes", wintypes.DWORD)]


class _DocInfo1(ctypes.Structure):
    _fields_ = [("pDocName", wintypes.LPWSTR),
                ("pOutputFile", wintypes.LPWSTR),
                ("pDatatype", wintypes.LPWSTR)]


def list_printers() -> list[str]:
    """Every printer this PC can print to, for the Settings screen. Empty off Windows."""
    if not available():
        return []
    winspool = _winspool()
    flags = _ENUM_LOCAL | _ENUM_CONNECTIONS
    needed = wintypes.DWORD(0)
    returned = wintypes.DWORD(0)
    winspool.EnumPrintersW(flags, None, _LEVEL, None, 0, ctypes.byref(needed),
                           ctypes.byref(returned))
    if not needed.value:
        return []
    buffer = ctypes.create_string_buffer(needed.value)
    if not winspool.EnumPrintersW(flags, None, _LEVEL, buffer, needed, ctypes.byref(needed),
                                  ctypes.byref(returned)):
        raise WindowsPrintError(f"Windows could not list its printers (error "
                                f"{ctypes.get_last_error()}).")
    infos = ctypes.cast(buffer, ctypes.POINTER(_PrinterInfo4))
    return [infos[i].pPrinterName for i in range(returned.value) if infos[i].pPrinterName]


def send_raw(printer_name: str, data: bytes, *, job_name: str = "Sukoon receipt") -> None:
    """Hand ESC/POS bytes to a Windows printer, unchanged."""
    winspool = _winspool()
    handle = wintypes.HANDLE()
    if not winspool.OpenPrinterW(printer_name, ctypes.byref(handle), None):
        raise WindowsPrintError(
            f"Windows could not open the printer {printer_name!r} (error "
            f"{ctypes.get_last_error()}). Check the name on the Settings screen.")
    try:
        doc = _DocInfo1(job_name, None, "RAW")
        job = winspool.StartDocPrinterW(handle, 1, ctypes.byref(doc))
        if not job:
            raise WindowsPrintError(f"Windows refused the print job (error "
                                    f"{ctypes.get_last_error()}).")
        try:
            if not winspool.StartPagePrinter(handle):
                raise WindowsPrintError(f"Windows refused the page (error "
                                        f"{ctypes.get_last_error()}).")
            written = wintypes.DWORD(0)
            buffer = ctypes.create_string_buffer(data, len(data))
            if not winspool.WritePrinter(handle, buffer, len(data), ctypes.byref(written)):
                raise WindowsPrintError(f"Windows could not send the receipt (error "
                                        f"{ctypes.get_last_error()}).")
            if written.value != len(data):
                raise WindowsPrintError(
                    f"Only {written.value} of {len(data)} bytes reached the printer.")
            winspool.EndPagePrinter(handle)
        finally:
            winspool.EndDocPrinter(handle)
    finally:
        winspool.ClosePrinter(handle)
