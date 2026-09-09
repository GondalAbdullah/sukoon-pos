# 0001 — Technology Stack

Status: **Accepted** 2026-09-10 — confirmed by the client without amendment; not
independently stress-tested this session, as recorded in context.md.
Date: 2026-09-06
Phase: 0

## Context

Sukoon is a single-store inventory and point-of-sale system that must run entirely
on one PC inside a shop, be reachable from other in-shop terminals over the LAN,
install like a normal Windows program, and keep working with the network adapter
disabled. The only component permitted to need the internet is WhatsApp
notification delivery, and its absence must never block a sale.

The Development Specification (5) already states a full stack and its reasoning.
This ADR records that stack so it is citable as a binding decision rather than a
table in a brief, per Operating Rule 3.

## Decision

| Layer | Choice |
|---|---|
| Language / runtime | Python 3.11+ |
| Web framework | Flask 3.x (synchronous) |
| ORM / migrations | SQLAlchemy 2.x + Alembic via Flask-Migrate |
| Database | SQLite in WAL mode, single file on local disk |
| Auth | Flask-Login + Werkzeug password hashing |
| Templating / interactivity | Jinja2 server-rendered + htmx + Alpine.js |
| Styling | Tailwind CSS, compiled once at build time to a static stylesheet |
| Desktop wrapper | pywebview |
| Packaging | PyInstaller (onedir) + Inno Setup |
| Receipt printing | python-escpos, with PDF fallback |
| Barcode / QR generation | python-barcode, qrcode |
| PDF generation | ReportLab |
| Background jobs | APScheduler, in-process |
| Testing | pytest, pytest-flask, coverage.py |
| Logging | Python logging with a rotating file handler |

Every Flask route returns HTML, never JSON. No Node.js runtime ships inside the
installer; Tailwind is compiled by the developer and only the resulting `.css` is
bundled. No CDN is referenced anywhere in the shipped application: fonts and icons
are served from local static files (Design System 10.1).

## Alternatives Considered

- **PostgreSQL / MySQL instead of SQLite** — rejected. A separate database service
  to install, run, and maintain on a shop PC is real operational weight that a
  single store does not earn. Trade-off accepted: limited concurrent-write
  throughput, and a migration would be needed to reach multi-store.
- **FastAPI or Django instead of Flask** — rejected. FastAPI's async model solves a
  concurrency problem this deployment does not have; Django brings more baked-in
  assumptions than the project needs. Flask packages most cleanly into one
  executable.
- **A full SPA (React/Vue) instead of htmx + Alpine** — rejected. It would add a JS
  build pipeline and a JSON API layer to design, version, and test, for no gain on
  screens that are fundamentally forms and lists. Trade-off accepted: less suited
  to a heavily animated screen, which the Design System explicitly does not ask for
  (7: "prefer no animation over an uncertain one").
- **Electron instead of pywebview** — rejected. Bundling a second browser engine and
  a Node runtime for a window frame, when Python is already required. Trade-off
  accepted: depends on the Windows WebView2 runtime being present.
- **Celery + Redis instead of APScheduler** — rejected. A broker daemon on an
  offline single shop PC is infrastructure standing up to solve a smaller problem.
- **WeasyPrint instead of ReportLab** — rejected. WeasyPrint needs Cairo and Pango,
  which are painful to bundle into a PyInstaller Windows executable.
- **PyInstaller onefile instead of onedir** — rejected. Onedir starts noticeably
  faster and is far easier to diagnose when something is missing at runtime. The
  Inno Setup installer hides the folder from the shop owner either way.

## Consequences

**Easier:** one process, one file to back up, no services to administer on the shop
PC. The whole application can be reasoned about and tested locally with no
infrastructure. Packaging has one well-trodden path.

**Harder:** SQLite's single-writer model means concurrent-write correctness has to
be designed deliberately rather than assumed (invoice numbering, stock deduction).
Windows packaging cannot be meaningfully tested on a non-Windows machine.

**Forecloses:** multi-store synchronisation and cloud access without a real
migration. Any screen that genuinely needs SPA-level richness would be a new,
separately grilled decision, not a retrofit of this one.
