"""Inference-only descriptive residual statistics; no reference-position inputs."""

import math
from collections import defaultdict

import numpy as np


def moments(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return dict(count=0, mean_hz=None, median_hz=None, std_hz=None, rms_hz=None)
    return dict(
        count=len(values),
        mean_hz=float(np.mean(values)),
        median_hz=float(np.median(values)),
        std_hz=float(np.std(values)),
        rms_hz=float(np.sqrt(np.mean(values * values))),
    )


def correlation(left, right):
    """Undefined for fewer than two pairs or either constant series."""
    left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if len(left) < 2 or np.std(left) == 0 or np.std(right) == 0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def summarize_residuals(rows):
    """Require frozen fitted assignments >0.5; exact rounded-ms RX joins only.

    RX1 minus RX0 is evaluated within the same satellite and channel. Duplicate
    observations at a receiver/key are averaged before joining. Serial statistics
    use those averaged groups and only adjacent times separated by (0, 2] seconds.
    Standard deviations are population descriptions, not uncertainty estimates.
    """
    counts = dict(total=len(rows), assigned=0, eligible_assignment=0, noise=0, nonfinite=0)
    accepted = []
    grouped = defaultdict(list)
    for row in rows:
        if row["satellite"] <= 0:
            counts["noise"] += 1
            continue
        counts["assigned"] += 1
        fields = (row["time_s"], row["residual_hz"], row["assignment_probability"])
        if not all(math.isfinite(v) for v in fields):
            counts["nonfinite"] += 1
            continue
        if row["assignment_probability"] <= 0.5:
            continue
        counts["eligible_assignment"] += 1
        accepted.append(row)
        # Python round uses nearest integer, ties to even, explicitly frozen here.
        key = (row["receiver"], row["satellite"], row["channel"], round(row["time_s"] * 1000))
        grouped[key].append(row["residual_hz"])
    means = {key: float(np.mean(values)) for key, values in grouped.items()}
    differences = defaultdict(list)
    for (receiver, satellite, channel, tick), residual in sorted(means.items()):
        counterpart = (0, satellite, channel, tick)
        if receiver == 1 and counterpart in means:
            differences[satellite].append(residual - means[counterpart])
    satellites = []
    for satellite, values in sorted(differences.items()):
        stats = moments(values)
        stats["pair_count"] = stats.pop("count")
        satellites.append(dict(satellite=satellite, eligible=len(values) >= 10, **stats))
    eligible = sum(row["eligible"] for row in satellites)
    receiver_pairs = dict(
        orientation="RX1-RX0",
        pairs_total=sum(map(len, differences.values())),
        eligible_satellite_count=eligible,
        no_op=eligible < 2,
        satellites=satellites,
    )
    series = defaultdict(list)
    for (receiver, satellite, channel, tick), residual in means.items():
        series[receiver, satellite, channel].append((tick, residual))
    serial = []
    for (receiver, satellite, channel), values in sorted(series.items()):
        values.sort()
        pairs = [
            (a[1], b[1])
            for a, b in zip(values, values[1:], strict=False)
            if 0 < b[0] - a[0] <= 2000
        ]
        serial.append(
            dict(
                receiver=receiver,
                satellite=satellite,
                channel=channel,
                pair_count=len(pairs),
                eligible=len(pairs) >= 10,
                correlation=correlation(*zip(*pairs, strict=True)) if len(pairs) >= 10 else None,
            )
        )
    margin_rows = [r for r in accepted if math.isfinite(r["margin"])]
    margin_values = [r["margin"] for r in margin_rows]
    residual_values = [r["residual_hz"] for r in margin_rows]
    quartiles = []
    if margin_rows:
        ordered = sorted(margin_rows, key=lambda r: r["margin"])
        for ordinal, indices in enumerate(np.array_split(np.arange(len(ordered)), 4)):
            members = [ordered[int(i)] for i in indices]
            quartiles.append(
                dict(
                    quartile=ordinal + 1,
                    margin_min=min((r["margin"] for r in members), default=None),
                    margin_max=max((r["margin"] for r in members), default=None),
                    **moments([r["residual_hz"] for r in members]),
                )
            )
    margin = dict(
        description="GLRT margin; descriptive only, no variance calibration",
        count=len(margin_rows),
        correlation_residual=correlation(margin_values, residual_values),
        correlation_abs_residual=correlation(margin_values, np.abs(residual_values)),
        quartile_groups=quartiles,
    )
    residuals = moments([r["residual_hz"] for r in accepted])
    absolute = np.abs([r["residual_hz"] for r in accepted])
    residuals.update(
        median_abs_hz=float(np.median(absolute)) if len(absolute) else None,
        p95_abs_hz=float(np.percentile(absolute, 95)) if len(absolute) else None,
    )
    return dict(
        counts=counts,
        residuals=residuals,
        receiver_pairs=receiver_pairs,
        serial_groups=serial,
        margin=margin,
    )
