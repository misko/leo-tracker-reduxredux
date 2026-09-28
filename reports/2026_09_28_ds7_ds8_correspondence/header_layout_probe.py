"""Bounded exploratory header serialization search with fixed evaluation pairs.

Reuses previously inspected UT frames: evaluation is disjoint within this assay,
not a new prospective holdout. No field interpretation or FEC decode is implied.
"""

import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
from header_code_probe import best_check, check_score  # noqa: E402


def windows(rows, phase, pair, blocked):
    chunks = []
    for row in rows:
        usable = row[phase : phase + (len(row) - phase) // 3 * 3]
        triples = usable.reshape(3, -1).T if blocked else usable.reshape(-1, 3)
        chunks.append(
            np.lib.stride_tricks.sliding_window_view(triples[:, pair], 7, axis=0).reshape(-1, 14)
        )
    return np.concatenate(chunks).astype(np.uint8)


def lane_order(length, lanes):
    indices = np.arange(length)
    return np.lexsort((indices // lanes, indices % lanes))


def main():
    path = ROOT / "reports/2026_09_27_ut_header/local/fullband/soft_deviations.npz"
    data = np.load(path)
    bins = data["subcarriers"]
    bits = (data["deviations"][:, np.array([3, 5, 6, 7]) - 2].real > 0).astype(np.uint8)
    partition = np.random.default_rng(20260929).permutation(7)
    trials = []
    for order_name, order in [
        ("physical", np.argsort(np.fft.fftfreq(1024)[bins])),
        ("fft", np.arange(len(bins))),
    ]:
        for direction, lanes, blocked in itertools.product(
            [1, -1], [1, 4, 8, 16, 32], [False, True]
        ):
            ordered = bits[:, :, order[::direction][lane_order(len(bins), lanes)]]
            pairs = [ordered[a] ^ ordered[b] for a, b in partition[:6].reshape(3, 2)]
            for phase, streams in itertools.product(range(3), itertools.combinations(range(3), 2)):
                w = [windows(p, phase, streams, blocked) for p in pairs]
                mask, score = best_check(w[0])
                trials.append(
                    dict(
                        order=order_name,
                        direction=direction,
                        lanes=lanes,
                        blocked=blocked,
                        phase=phase,
                        streams=streams,
                        mask=mask,
                        discovery=score,
                        evaluation=check_score(w[1], mask),
                        final=check_score(w[2], mask),
                    )
                )
    selected = max(trials, key=lambda t: abs(t["discovery"]))
    output = dict(
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        frame_pairs=(partition[:6].reshape(3, 2) + 250).tolist(),
        unused_frame=int(partition[6] + 250),
        selected_by_discovery_only=selected,
        trials=trials,
        scope="Even-weight two-stream seven-tap parity checks; direct/blocked rate-1/3 "
        "serialization, two carrier orders, both directions, 1/4/8/16/32 lane grouping.",
        limitations="Previously inspected frames reused. Unknown polarity cancels only for "
        "tested even-weight checks. No arbitrary interleaver search or semantic decode.",
    )
    target = Path(__file__).parent / "local/header-layout-probe.json"
    target.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "trials"}, indent=2))


if __name__ == "__main__":
    main()
