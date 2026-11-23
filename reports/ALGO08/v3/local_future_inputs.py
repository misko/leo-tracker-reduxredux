"""Original receiver opportunities for the bounded local repair."""

from bidirectional_selection import supported


MAX_GAP_S = 8.


def future_observations(native, forward):
    from leo.analysis.localization_v3.tracks import winning_observations

    original = native["source"]["probes"]
    backward_or_forward, counts = supported(original)
    forward_probes = forward["source"]["probes"]
    missing = [row if not past["candidates"] else dict(row, candidates=[])
               for row, past in zip(backward_or_forward, forward_probes, strict=True)]
    rows, _ = winning_observations(dict(native, source=dict(native["source"], probes=missing)))
    if len(rows) != counts["future_only"]:
        raise ValueError("The unseen future-supported factors differ from the locked two-sided rule")
    return rows


def lane(row):
    return row["receiver"], row["channel"], row["actual_rf_hz"]
