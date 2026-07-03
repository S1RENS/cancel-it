def calculate_outcome(poll_data: dict) -> None:
    """
    Determines the outcome of a poll based on votes.
    Mutates poll_data["status"] in place.
    """
    votes = poll_data["votes"]
    participants = poll_data["participants"]

    # A. Initialization: Map raw votes to effective states
    effective_votes = {}

    for user, data in votes.items():
        v_type = data["type"]
        if v_type == "hard":
            effective_votes[user] = "cancel"
        elif v_type == "go":
            effective_votes[user] = "go"
        elif v_type == "soft":
            # Soft cancel counts towards threshold immediately
            effective_votes[user] = "cancel"
        else:
            effective_votes[user] = "pending"  # Conditional

    # B. Chain Resolution (Iterative)
    changes = True
    while changes:
        changes = False
        for user, data in votes.items():
            if data["type"] == "conditional":
                target = data["target"]

                # Ensure target exists in effective votes before checking
                if target not in effective_votes:
                    continue

                target_status = effective_votes[target]
                current_status = effective_votes[user]

                new_status = current_status
                if target_status == "go":
                    new_status = "go"
                elif target_status == "cancel":
                    new_status = "cancel"

                if new_status != current_status:
                    effective_votes[user] = new_status
                    changes = True

    # C. Deadlock Resolution (The "Mutual Pact")
    # If still 'pending', it's a circular loop. Treat as GO.
    for user, status in effective_votes.items():
        if status == "pending":
            effective_votes[user] = "go"

    # D. Final Tally
    cancel_count = sum(1 for status in effective_votes.values() if status == "cancel")
    total_participants = len(participants)
    # Threshold is > 50%
    threshold = total_participants / 2

    if cancel_count > threshold:
        poll_data["status"] = "cancelled"
    else:
        poll_data["status"] = "confirmed"
