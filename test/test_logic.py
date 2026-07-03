import pytest

import logic


def test_simple_majority_go():
    """Scenario: 3 people, 2 GO, 1 Soft Cancel -> Confirmed"""
    poll_data = {
        "participants": ["A", "B", "C"],
        "votes": {
            "A": {"type": "go"},
            "B": {"type": "go"},
            "C": {"type": "soft"},
        },
        "status": "active",
    }
    logic.calculate_outcome(poll_data)
    assert poll_data["status"] == "confirmed"


def test_wingman_cancel_chain():
    """Scenario: Alice needs Bob. Bob hard cancels. Both should cancel."""
    poll_data = {
        "participants": ["Alice", "Bob"],
        "votes": {
            "Alice": {"type": "conditional", "target": "Bob"},
            "Bob": {"type": "hard"},
        },
        "status": "active",
    }
    logic.calculate_outcome(poll_data)
    # Alice follows Bob (Cancel). 2/2 Cancelled.
    assert poll_data["status"] == "cancelled"


def test_circular_deadlock():
    """Scenario: The 'Blood Pact'. A needs B, B needs A. Should resolve to GO."""
    poll_data = {
        "participants": ["A", "B"],
        "votes": {
            "A": {"type": "conditional", "target": "B"},
            "B": {"type": "conditional", "target": "A"},
        },
        "status": "active",
    }
    logic.calculate_outcome(poll_data)
    assert poll_data["status"] == "confirmed"


@pytest.mark.parametrize(
    "votes, expected_status",
    [
        # Case 1: 50/50 Split (Soft cancel counts as cancel)
        (
            {"A": {"type": "go"}, "B": {"type": "soft"}},
            "confirmed",  # 1 cancel out of 2 is exactly 50%, needs > 50% to cancel
        ),
        # Case 2: Hard Cancel Minority
        (
            {"A": {"type": "go"}, "B": {"type": "go"}, "C": {"type": "hard"}},
            "confirmed",
        ),
        # Case 3: Empty votes (Wait logic handles this, but logic shouldn't crash)
        (
            {},
            "confirmed",  # 0 cancels out of 3 is < threshold
        ),
    ],
)
def test_outcome_variations(votes, expected_status):
    """Tests multiple scenarios using one function definition."""
    poll_data = {
        "participants": ["A", "B", "C"],  # Dummy participants
        "votes": votes,
        "status": "active",
    }
    logic.calculate_outcome(poll_data)
    assert poll_data["status"] == expected_status


def test_broken_chain_domino():
    """Scenario: A needs B, B needs C, C hard cancels -> all cancel."""
    poll_data = {
        "participants": ["Alice", "Bob", "Charlie"],
        "votes": {
            "Alice": {"type": "conditional", "target": "Bob"},
            "Bob": {"type": "conditional", "target": "Charlie"},
            "Charlie": {"type": "hard"},
        },
        "status": "active",
    }
    logic.calculate_outcome(poll_data)
    assert poll_data["status"] == "cancelled"
