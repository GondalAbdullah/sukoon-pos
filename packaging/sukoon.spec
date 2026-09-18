# PyInstaller spec — onedir (ADR-0001), two programs in one folder:
#   sukoon-server.exe  the boot task that serves every till (console build: a task running
#                      under the Sukoon account shows no window, and a console build keeps
#                      stdout/stderr valid so a failure to start is never silent)
#   Sukoon.exe         the owner's pywebview window (windowed build)
# Build on Windows, from the repository root:  pyinstaller packaging\sukoon.spec
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = SPECPATH + "\\.."

datas = [
    (ROOT + "\\sukoon\\templates", "sukoon\\templates"),
    (ROOT + "\\sukoon\\static", "sukoon\\static"),
    (ROOT + "\\migrations", "migrations"),       # startup.migrations_dir() reads _MEIPASS
]
datas += collect_data_files("tzdata")           # Asia/Karachi on Windows (ADR-0024)
datas += collect_data_files("reportlab")        # fonts for receipts, statements, labels
datas += collect_data_files("barcode")
datas += collect_data_files("escpos")

hidden = (
    collect_submodules("sukoon")                # blueprints are imported inside create_app
    + collect_submodules("alembic")
    + ["waitress", "flask_migrate", "sqlalchemy.dialects.sqlite",
       # migrations/env.py is read from disk at start-up, so PyInstaller never sees its imports.
       # Without this the first real build refused to start: "No module named 'logging.config'".
       "logging.config"]
)

server = Analysis([ROOT + "\\packaging\\server_entry.py"], pathex=[ROOT], datas=datas,
                  hiddenimports=hidden, excludes=["tkinter", "pytest"])
window = Analysis([ROOT + "\\packaging\\window_entry.py"], pathex=[ROOT],
                  hiddenimports=["webview", "clr_loader", "pythonnet"],
                  excludes=["tkinter", "pytest"])

ICON = ROOT + "\\packaging\\sukoon.ico"

server_exe = EXE(PYZ(server.pure), server.scripts, [], exclude_binaries=True,
                 name="sukoon-server", console=True, icon=ICON)
window_exe = EXE(PYZ(window.pure), window.scripts, [], exclude_binaries=True,
                 name="Sukoon", console=False, icon=ICON)

COLLECT(server_exe, server.binaries, server.datas,
        window_exe, window.binaries, window.datas,
        name="Sukoon")
