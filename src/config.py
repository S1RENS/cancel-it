# Configuration constants
import os

MAX_PARTICIPANTS = 20
POLL_ID_LENGTH = 8  # characters of the URL-safe poll id
APP_TITLE = "Cancel-It"
APP_ICON = "🚫"

DEFAULT_DB_PATH = "data/cancelit.db"


def db_path() -> str:
    """Path to the SQLite database, overridable via CANCELIT_DB_PATH."""
    return os.environ.get("CANCELIT_DB_PATH", DEFAULT_DB_PATH)
