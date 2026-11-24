"""Pure source-derived aperture arithmetic for the qualified 20/8 ms verifier."""

from statistics import mean


RATE = 10_000_000


def centroid(factor, short):
    """Return equal-frame verifier and delay-product centroids and verifier frame count."""
    offset = factor["fractional_epoch_offset_samples"]
    base = factor["integer_epoch_sample"]
    sample_count, maximum = (80_000, 5) if short else (200_000, 15)
    integer = abs(offset-round(offset)) <= 1e-12
    starts = []
    for frame in range(maximum):
        start = base + (40_000*frame+1)//3 + 88 + offset
        if start < (0 if integer else 7) or start + 64*44 - 1 >= sample_count - (0 if integer else 8):
            break
        starts.append(start)
    if not starts:
        raise ValueError("The retained factor has no native verifier support")
    verifier = (mean(starts) + (64*44-1)/2) / RATE
    # The refined scout origin is represented by the chosen exported epoch.
    delay = (base + 88 + (64*44-1)/2 + mean((40_000*j+1)//3 for j in range(5 if short else 14))) / RATE
    return verifier, len(starts), delay


def graph_rows(rows, corrections):
    """Replace only times after requiring exact native identities and nominal coordinates."""
    if corrections.keys() != {row["observation_id"] for row in rows} or len(rows) != len(corrections):
        raise ValueError("Timestamp correction and Graph disagree on the original winners")
    adjusted = []
    for row in rows:
        nominal, offset, cfo = corrections[row["observation_id"]]
        if nominal != row["time_s"] or cfo != row["measured_cfo_hz"]:
            raise ValueError("Timestamp correction and Graph disagree on original coordinates")
        adjusted.append(dict(row, time_s=nominal+offset) if offset else row)
    return sorted(adjusted, key=lambda r: (r["receiver"], r["channel"], r["time_s"], r["observation_id"]))
