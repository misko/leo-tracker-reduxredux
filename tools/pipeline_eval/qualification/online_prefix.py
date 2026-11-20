"""Construct independently causal native replay inputs and evaluate an online stop rule."""

from unittest.mock import patch

from ..scoring import distance_km
from ..variants import contiguous_prefix

HORIZONS = (120, 180, 240, 300)
MAX_DISAGREEMENT_KM = 1.0
MIN_SHARED_ORBITS = 4
MIN_FRESH_ORBITS = 2


def snapshot(document, cutoff):
    source, provenance, anchor = (document[k] for k in ("source", "provenance", "clock_anchor"))
    rate = source["sample_rate_hz"]
    relative_end = document["last_sample_counter"] - anchor["sample_counter"]
    full = cutoff is None or cutoff * rate >= relative_end
    options = patch.object(contiguous_prefix, "PREFIX_SECONDS", HORIZONS[0] if full else cutoff)
    with options:
        prefix, audit = contiguous_prefix.restrict(document, prefix=not full)
    # Supply only the receiver's clock, completed visits and the native reader's source fields.
    source_fields = ("probe_ms", "sample_rate_hz", "session_id", "probes")
    updated = prefix["source"]
    document = dict(
        clock_anchor=anchor,
        last_sample_counter=prefix["last_sample_counter"],
        delivery_clocks=prefix["delivery_clocks"],
        source={k: updated[k] for k in source_fields},
        provenance={
            k: prefix["provenance"][k]
            for k in (
                "window_count",
                "processed_windows",
                "invalid_capture",
                "excluded_windows",
            )
        },
    )
    declared = audit["last_input_sample_s"] if cutoff is None else cutoff
    return document, dict(
        nominal_checkpoint_s=declared,
        uses_complete_capture=full,
        available_at_elapsed_s=[max(declared, t) for t in audit["last_input_delivery_elapsed_s"]],
        actual_last_sample_s=audit["last_input_sample_s"],
        expected_probes=len(updated["probes"]),
        scheduled_visits=audit["scheduled_visits"],
        valid_visits=audit["valid_visits"],
        excluded_visits=audit["excluded_visits"],
        first_counter=anchor["sample_counter"],
        last_sample_counter=prefix["last_sample_counter"],
        first_noncausal_end_counter=audit["next_sample_end_counter"],
        original_window_count=provenance["window_count"],
    )


def agrees(earlier, current, arm):
    a = earlier["result"]["arms"][arm]["latlon"]
    b = current["result"]["arms"][arm]["latlon"]
    distance = distance_km(a, b)
    old = earlier.get("orbit_support", {}).get(arm, {})
    new = current.get("orbit_support", {}).get(arm, {})
    common = old.keys() & new.keys()
    closed = earlier["capture"]["actual_last_sample_s"]
    added = {i for i in common if new[i]["latest_s"] > closed}
    accepted = (
        distance is not None
        and distance <= MAX_DISAGREEMENT_KM
        and len(common) >= MIN_SHARED_ORBITS
        and len(added) >= MIN_FRESH_ORBITS
    )
    return dict(
        agreement=accepted,
        displacement_km=distance,
        shared_orbits=len(common),
        refreshed_shared_orbits=len(added),
    )


def stable_stop(rows, arm):
    checkpoints = [row["checkpoint"] for row in rows]
    if tuple(checkpoints) != HORIZONS:
        raise ValueError("prospective stop policy requires the native checkpoints in order")
    decisions = [agrees(a, b, arm) for a, b in zip(rows, rows[1:], strict=False)]
    chosen = next((i for i, row in enumerate(decisions, 1) if row["agreement"]), len(rows) - 1)
    reason = "adjacent agreement" if decisions[chosen - 1]["agreement"] else "ordinary deadline"
    return chosen, reason, decisions


def timeline(rows):
    """Scenario for serial CPU work overlapping acquisition as each cutoff is delivered."""
    available = [0.0, 0.0]
    outcomes = []
    for row in rows:
        if row.get("worker_wall_s") is None:
            outcomes.append(None)
            continue
        arrival = row["capture"]["available_at_elapsed_s"]
        available = [
            max(p, c) + row["worker_wall_s"] for p, c in zip(available, arrival, strict=True)
        ]
        outcomes.append(available)
    return outcomes
