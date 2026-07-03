import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import storage


def _time_travel(monkeypatch, hours: float) -> None:
    """Make storage believe `hours` have passed."""
    offset = hours * 3600
    monkeypatch.setattr(storage, "_now", lambda: time.time() + offset)


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CANCELIT_DB_PATH", str(tmp_path / "test.db"))


def test_create_and_get_roundtrip():
    poll_id = storage.create_poll(["Alice", "Bob"], name="Friday dinner")
    poll = storage.get_poll(poll_id)
    deadline = poll.pop("deadline")
    assert poll == {
        "name": "Friday dinner",
        "participants": ["Alice", "Bob"],
        "votes": {},
        "status": "active",
    }
    expected = time.time() + storage.DEFAULT_POLL_DURATION_HOURS * 3600
    assert abs(deadline - expected) < 60


@pytest.mark.parametrize("bad_duration", [0, -1, 24 * 7 + 1])
def test_invalid_duration_rejected(bad_duration):
    with pytest.raises(ValueError):
        storage.create_poll(["A", "B"], duration_hours=bad_duration)


@pytest.mark.parametrize("duration_hours", [0.25, 24 * 7])
def test_duration_range_minutes_to_a_week(duration_hours, monkeypatch):
    poll_id = storage.create_poll(["A", "B"], duration_hours=duration_hours)
    expected = time.time() + duration_hours * 3600
    assert abs(storage.get_poll(poll_id)["deadline"] - expected) < 60

    # expires right after its window, not before
    _time_travel(monkeypatch, duration_hours * 0.9)
    assert storage.get_poll(poll_id)["status"] == "active"
    _time_travel(monkeypatch, duration_hours * 1.1)
    assert storage.get_poll(poll_id)["status"] != "active"


def test_poll_ids_are_short_and_unique():
    ids = {storage.create_poll(["A", "B"]) for _ in range(50)}
    assert len(ids) == 50
    assert all(len(poll_id) == 8 for poll_id in ids)


def test_get_unknown_poll_returns_none():
    assert storage.get_poll("nope1234") is None


def test_cast_vote_records_vote():
    poll_id = storage.create_poll(["A", "B"])
    poll, accepted = storage.cast_vote(poll_id, "A", {"type": "go"})
    assert accepted is True
    assert poll["votes"]["A"] == {"type": "go"}
    assert storage.get_poll(poll_id)["votes"]["A"] == {"type": "go"}


def test_first_vote_wins():
    poll_id = storage.create_poll(["A", "B"])
    storage.cast_vote(poll_id, "A", {"type": "go"})
    poll, accepted = storage.cast_vote(poll_id, "A", {"type": "hard"})
    assert accepted is False
    assert poll["votes"]["A"] == {"type": "go"}


def test_vote_on_unknown_poll_raises():
    with pytest.raises(storage.PollNotFoundError):
        storage.cast_vote("nope1234", "A", {"type": "go"})


@pytest.mark.parametrize(
    "voter, vote",
    [
        ("Mallory", {"type": "go"}),  # not a participant
        ("A", {"type": "maybe"}),  # invalid vote type
        ("A", {}),  # missing type
        ("A", {"type": "conditional", "target": "A"}),  # wingman = self
        ("A", {"type": "conditional", "target": "Zoe"}),  # unknown wingman
    ],
)
def test_invalid_votes_raise(voter, vote):
    poll_id = storage.create_poll(["A", "B"])
    with pytest.raises(ValueError):
        storage.cast_vote(poll_id, voter, vote)


def test_last_vote_concludes_and_persists():
    poll_id = storage.create_poll(["A", "B", "C"])
    storage.cast_vote(poll_id, "A", {"type": "hard"})
    storage.cast_vote(poll_id, "B", {"type": "soft"})
    assert storage.get_poll(poll_id)["status"] == "active"
    poll, accepted = storage.cast_vote(poll_id, "C", {"type": "go"})
    assert accepted is True
    assert poll["status"] == "cancelled"
    # a fresh read sees the concluded state (persistence)
    assert storage.get_poll(poll_id)["status"] == "cancelled"


def test_vote_on_concluded_poll_raises():
    poll_id = storage.create_poll(["A", "B"])
    storage.cast_vote(poll_id, "A", {"type": "go"})
    storage.cast_vote(poll_id, "B", {"type": "go"})
    with pytest.raises(storage.PollConcludedError):
        storage.cast_vote(poll_id, "A", {"type": "hard"})


def test_expired_poll_finalizes_on_read(monkeypatch):
    poll_id = storage.create_poll(["A", "B", "C"], duration_hours=1)
    storage.cast_vote(poll_id, "A", {"type": "hard"})
    storage.cast_vote(poll_id, "B", {"type": "hard"})

    _time_travel(monkeypatch, 2)
    poll = storage.get_poll(poll_id)
    # 2 cancels of 3 participants is a majority; C's silence counts as go
    assert poll["status"] == "cancelled"
    assert poll["timed_out"] is True

    # concluded state persisted, and stays concluded at normal time too
    monkeypatch.setattr(storage, "_now", time.time)
    assert storage.get_poll(poll_id)["status"] == "cancelled"


def test_expired_poll_with_minority_cancel_confirms(monkeypatch):
    poll_id = storage.create_poll(["A", "B", "C"], duration_hours=1)
    storage.cast_vote(poll_id, "A", {"type": "soft"})

    _time_travel(monkeypatch, 2)
    poll = storage.get_poll(poll_id)
    # 1 cancel of 3 is no majority: the event stands
    assert poll["status"] == "confirmed"
    assert poll["timed_out"] is True


def test_vote_after_deadline_rejected_and_finalizes(monkeypatch):
    poll_id = storage.create_poll(["A", "B"], duration_hours=1)
    storage.cast_vote(poll_id, "A", {"type": "go"})

    _time_travel(monkeypatch, 2)
    with pytest.raises(storage.PollConcludedError):
        storage.cast_vote(poll_id, "B", {"type": "hard"})
    poll = storage.get_poll(poll_id)
    assert poll["status"] == "confirmed"
    assert poll["timed_out"] is True
    assert "B" not in poll["votes"]


def test_poll_without_deadline_never_expires():
    # polls created before the deadline feature have no "deadline" key
    poll_id = storage.create_poll(["A", "B"])
    conn = storage._connect()
    try:
        conn.execute(
            "UPDATE polls SET data = ? WHERE id = ?",
            (
                '{"name": "", "participants": ["A", "B"], '
                '"votes": {}, "status": "active"}',
                poll_id,
            ),
        )
    finally:
        conn.close()
    poll = storage.get_poll(poll_id)
    assert poll["status"] == "active"
    _, accepted = storage.cast_vote(poll_id, "A", {"type": "go"})
    assert accepted is True


def test_concurrent_votes_all_recorded_once():
    participants = [f"P{i}" for i in range(8)]
    poll_id = storage.create_poll(participants)
    votes = [{"type": t} for t in ("go", "soft", "hard", "go") * 2]

    def vote(args):
        voter, v = args
        return storage.cast_vote(poll_id, voter, v)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(vote, zip(participants, votes)))

    assert all(accepted for _, accepted in results)
    poll = storage.get_poll(poll_id)
    assert len(poll["votes"]) == 8
    # 4 cancels of 8 is not > 50%, so the event stands
    assert poll["status"] == "confirmed"
