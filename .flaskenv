# Read by the `flask` command only (python-dotenv), so `flask db upgrade`, `flask seed` and
# `flask run` find Sukoon without exporting anything. No secrets here; those go in .env.
FLASK_APP=sukoon.app
