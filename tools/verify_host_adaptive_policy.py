"""Independent saved-trace policy check; no RF or native scheduler execution."""


def verify_policy(receipt):
    """Replay healthy applied evidence, using device HOPS basis as application time.

    Delivery acknowledgement alone does not claim application. This check binds
    the observed application frontier to host outcomes and compares every choice.
    """
    states = ["unknown"] * 8
    misses = [0] * 8
    detections = [None] * 8
    last_starts = [None] * 8
    credits = [0] * 8
    cursor = 0
    applied = -1
    maximum_revisit = 0
    maximum_apply_age = 0
    for index, event in enumerate(receipt.events):
        choice = event.decision
        now = choice.decision_counter
        basis = -1 if choice.basis_visit is None else choice.basis_visit
        if not applied <= basis < index or basis - applied > 8:
            raise ValueError(f"invalid application frontier at visit {index}")
        for source in range(applied + 1, basis + 1):
            record = receipt.host_decisions[source]
            age = now - record.valid_end_counter_exclusive
            if record.health != "healthy" or record.feedback_disposition != "accepted":
                raise ValueError(f"unhealthy or unaccepted applied source {source}")
            if not 0 <= age <= 10_000_000:
                raise ValueError(f"applied source age exceeds healthy gate at {source}")
            maximum_apply_age = max(maximum_apply_age, age)
            target = record.target_index
            if record.feedback_outcome == "detected":
                states[target] = "active"
                misses[target] = 0
                detections[target] = record.valid_end_counter_exclusive
            elif record.feedback_outcome == "not_detected":
                misses[target] = min(3, misses[target] + 1)
            else:
                misses[target] = 0
        applied = basis
        for target in range(8):
            if misses[target] == 3 and (
                detections[target] is None or now - detections[target] >= 20_000_000
            ):
                states[target] = "quiet"
        active = sum(1 << t for t in range(8) if states[t] == "active")
        quiet = sum(1 << t for t in range(8) if states[t] == "quiet")
        order = [(cursor + offset) % 8 for offset in range(8)]
        total = 0
        if index < 24 or not active:
            selected = cursor
            reason = "warmup" if index < 24 else "none_active"
            credits = [0] * 8
        else:
            weights = [1 if state == "quiet" else 3 for state in states]
            credits = [credit + weight for credit, weight in zip(credits, weights, strict=True)]
            total = sum(weights)
            selected = max(order, key=lambda t: credits[t])
            reason = "weighted"
            overdue = [t for t in order if now - last_starts[t] >= 28_400_000]
            if overdue:
                selected = min(overdue, key=lambda t: last_starts[t])
                reason = "exploration"
        remaining = (
            0 if detections[selected] is None else max(0, 20_000_000 - (now - detections[selected]))
        )
        expected = (selected, reason, active, quiet, misses[selected], remaining)
        actual = (
            choice.proposed_target,
            choice.reason,
            choice.active_mask,
            choice.quiet_mask,
            choice.consecutive_misses,
            choice.cooldown_remaining_samples,
        )
        if actual != expected:
            raise ValueError(f"policy mismatch at visit {index}: {actual} != {expected}")
        target = event.target_index
        if target != (index % 8 if choice.mode == "shadow" else selected):
            raise ValueError(f"actual target mismatch at visit {index}")
        if last_starts[target] is not None:
            maximum_revisit = max(maximum_revisit, event.valid_start_counter - last_starts[target])
        if total:
            credits[target] -= total
            credits = [max(-total, min(total, credit)) for credit in credits]
        last_starts[target] = event.valid_start_counter
        cursor = (target + 1) % 8
    if maximum_revisit > 30_000_000:
        raise ValueError("actual revisit exceeded three seconds")
    return {
        "verified_choices": len(receipt.events),
        "maximum_revisit_seconds": maximum_revisit / 10_000_000,
        "maximum_apply_age_seconds": maximum_apply_age / 10_000_000,
    }
