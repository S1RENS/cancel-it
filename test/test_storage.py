from concurrent.futures import ThreadPoolExecutor

import pytest

import storage


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CANCELIT_DB_PATH", str(tmp_path / "test.db"))


def test_create_and_get_roundtrip():
    poll_id = storage.create_poll(["Alice", "Bob"], name="Friday dinner")
    poll = storage.get_poll(poll_id)
    assert poll == {
        "name": "Friday dinner",
        "participants": ["Alice", "Bob"],
        "votes": {},
        "status": "active",
    }


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
