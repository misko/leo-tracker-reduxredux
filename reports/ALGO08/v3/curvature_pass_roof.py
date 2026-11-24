"""Desk audit of the saved cold-enrollment budget and three-time contrast."""

from fractions import Fraction
from gzip import decompress
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
TARGET_NS = 2_500_000_000
PINS = {
    "cold-exact-budget-dense-control.json.gz": "d5caefcf59182ded8f26176b2548e03a6d814d89dca98f081bc57e765600757d",
    "cold-exact-budget-profile.json.gz": "b274c063df2a39b76bedc00d146e4896fe6047b07b960cea5e9f6904976d0f0d",
    "catalogue-block-dense-pair.json.gz": "f018d6337a58a1c91014a9b36d1020555bbf9bdc31b39fc3c6f144eaa0a2c11b",
}


def contrast_weights(times):
    """Exact-real weights for the three distinct times supplied to this audit."""
    a, b, c = map(Fraction, times)
    if not a < b < c:
        raise ValueError("Three strictly increasing times required")
    return c - b, a - c, b - a


def whitened_floor(observed_contrast, predicted_interval, contrast_variance):
    """Conditional squared-loss floor given a sound interval and variance bound."""
    low, high = map(Fraction, predicted_interval)
    observed, variance = map(Fraction, (observed_contrast, contrast_variance))
    if low > high or variance <= 0:
        raise ValueError("Enclosing interval and positive variance required")
    distance = max(Fraction(0), low - observed, observed - high)
    return distance**2 / variance


def checked(name):
    data = decompress((HERE / "measurements" / name).read_bytes())
    if sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f"Cold archive changed: {name}")
    return json.loads(data)


def required_fraction(total_cpu_ns, overhead_ns=0):
    if total_cpu_ns <= 0 or overhead_ns < 0:
        raise ValueError("Positive scope and nonnegative overhead required")
    return Fraction(TARGET_NS + overhead_ns, total_cpu_ns)


def report():
    live = checked("cold-exact-budget-dense-control.json.gz")
    profile = checked("cold-exact-budget-profile.json.gz")
    block = checked("catalogue-block-dense-pair.json.gz")["result"]["rank"]["paired"]
    if not live["scientific_parity"] or not profile["scientific_parity"] or not block["cold_nodes_byte_equal"]:
        raise ValueError("The cost controls lack the recorded science checks")
    work = live["stages"]["work"]
    rank, = work["ranks"]
    cold, = work["scopes"]
    winner = work["selected"]["branch"]
    kept = (sum(row["cpu_ns"] for row in work["selected"]["prefix"] if row["branch"] == winner)
            + sum(row["cpu_ns"] for row in work["selected"]["completed"] if row["branch"] == winner))
    rows = profile["stages"]["work"]["profile_rows"]
    association, = [row for row in rows if row["function"] == "association" and row["file"].endswith("/scan.py")]
    statistics, = [row for row in rows if row["function"] == "statistics" and row["file"].endswith("/discovery.py")]
    measured = dict(rank=rank["cpu_ns"], whole_cold=cold["cpu_ns"], cold_less_required_winner=cold["cpu_ns"] - kept,
                    separate_rank_with_catalogue_blocks=block["candidate"]["cpu_ns"])
    fractions = {key: {str(overhead): float(required_fraction(nanos, overhead)) for overhead in (0, 250_000_000)}
                 for key, nanos in measured.items()}
    return dict(archive_sha256=PINS, target_cpu_ns=TARGET_NS, measured_cpu_ns=measured,
                required_fraction_of_paid_cpu=fractions, kept_winner_cpu_ns=kept,
                rank_signatures=len(work["ordered"]), finalist_prefixes=len(work["selected"]["prefix"]),
                profiled_association=dict(calls=association["calls"], cpu_s=association["inclusive_cpu_s"]),
                profiled_statistics=dict(calls=statistics["calls"], cpu_s=statistics["inclusive_cpu_s"]),
                disjoint_association_statistics_full_grant_cpu_s=association["inclusive_cpu_s"] + statistics["inclusive_cpu_s"],
                observed_block_rank_saving_cpu_ns=block["control"]["cpu_ns"] - block["candidate"]["cpu_ns"],
                timed_new_trials=0, waveform_reads=0)


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True, allow_nan=False))
