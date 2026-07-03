"""SQLite-backed poll storage.

Each poll is stored as a single JSON blob so the dict shape used by the app
and by logic.calculate_outcome stays unchanged:
{"name": str, "participants": [str], "votes": {str: {...}}, "status": str}

Concurrency: every write happens inside a BEGIN IMMEDIATE transaction, which
takes SQLite's write lock up front. Two people submitting the "last" vote at
the same time are serialized at the database level, so exactly one of them
triggers the outcome calculation and no vote is ever lost — correct across
threads and processes alike.
"""

import json
import os
import secrets
import sqlite3

import config
import logic

VALID_VOTE_TYPES = {"go", "soft", "hard", "conditional"}
POLL_RETENTION_DAYS = 30


class PollNotFoundError(Exception):
    pass


class PollConcludedError(Exception):
    pass


def _connect() -> sqlite3.Connection:
    path = config.db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # isolation_level=None -> autocommit; we issue BEGIN IMMEDIATE explicitly
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS polls (
            id         TEXT PRIMARY KEY,
            data       TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    return conn


def _new_poll_id() -> str:
    # token_urlsafe emits ~1.33 chars per byte; overshoot then trim
    return secrets.token_urlsafe(config.POLL_ID_LENGTH)[: config.POLL_ID_LENGTH]


def create_poll(participants: list[str], name: str = "") -> str:
    """Create a poll and return its id. Also prunes old polls."""
    poll = {
        "name": name,
        "participants": list(participants),
        "votes": {},
        "status": "active",
    }
    conn = _connect()
    try:
        poll_id = _new_poll_id()
        conn.execute(
            "INSERT INTO polls (id, data) VALUES (?, ?)",
            (poll_id, json.dumps(poll)),
        )
        conn.execute(
            "DELETE FROM polls WHERE created_at < datetime('now', ?)",
            (f"-{POLL_RETENTION_DAYS} days",),
        )
        return poll_id
    finally:
        conn.close()


def get_poll(poll_id: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM polls WHERE id = ?", (poll_id,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def cast_vote(poll_id: str, voter: str, vote: dict) -> tuple[dict, bool]:
    """Record a vote atomically. Returns (poll, accepted).

    accepted is False when the voter already voted (first vote wins).
    If this is the final vote, the outcome is resolved inside the same
    transaction, so conclusion happens exactly once.
    """
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT data FROM polls WHERE id = ?", (poll_id,)
            ).fetchone()
            if row is None:
                raise PollNotFoundError(poll_id)

            poll = json.loads(row[0])

            if poll["status"] != "active":
                raise PollConcludedError(poll_id)
            if voter not in poll["participants"]:
                raise ValueError(f"Unknown participant: {voter!r}")
            vote_type = vote.get("type")
            if vote_type not in VALID_VOTE_TYPES:
                raise ValueError(f"Invalid vote type: {vote_type!r}")
            if vote_type == "conditional":
                target = vote.get("target")
                if target not in poll["participants"] or target == voter:
                    raise ValueError(f"Invalid wingman target: {target!r}")

            if voter in poll["votes"]:
                conn.execute("ROLLBACK")
                return poll, False

            poll["votes"][voter] = vote
            if len(poll["votes"]) >= len(poll["participants"]):
                logic.calculate_outcome(poll)

            conn.execute(
                "UPDATE polls SET data = ? WHERE id = ?",
                (json.dumps(poll), poll_id),
            )
            conn.execute("COMMIT")
            return poll, True
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass  # transaction already closed
            raise
    finally:
        conn.close()
