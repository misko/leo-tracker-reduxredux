"""Measure how often independently verified antennas share a pilot proposal."""

import argparse
import json
import math
from collections import Counter
from contextlib import ExitStack
from itertools import permutations
from pathlib import Path

import numpy as np

from .receiver_benchmark import Receiver, digest, read_archive


def phase_distance(a, b):
    offset = (a[1] + a[2]) - (b[1] + b[2])
    return abs(math.remainder(offset, 13333.))


def paired_support(left, right, samples, hz=None):
    """Maximum number of distinct proposals, allowing each donor once."""
    width = max(len(left), len(right))
    padded = (*right, *((None,) * (width - len(right))))
    return max(sum(y is not None and phase_distance(x, y) <= samples and
                   (hz is None or abs(x[3] - y[3]) <= hz) for x, y in zip(left, ordered))
               for ordered in permutations(padded))


def audit(rows):
    result = dict(visit_states=Counter(), rx0_donor=Counter(), rx1_donor=Counter())
    for pair in rows:
        result["visit_states"][f"{len(pair[0])}/{len(pair[1])}"] += 1
        for lane in (0, 1):
            donor, other = pair[lane], pair[1 - lane]
            stat = result[f"rx{lane}_donor"]
            stat["target_factors"] += len(other)
            stat["target_factors_when_donor_empty"] += len(other) if not donor else 0
            stat["target_second_scan_factors"] += sum(f[0] == 1 for f in other)
            for width in (2, 8):
                count = paired_support(donor, other, width)
                stat[f"distinct_within_{width}_samples"] += count
                stat[f"target_positive_lanes_all_proposed_within_{width}_samples"] += bool(other) and count == len(other)
            stat["distinct_within_2_samples_and_1000_hz"] += paired_support(donor, other, 2, 1000)
            stat["second_scan_with_no_phase_within_2_samples"] += sum(
                f[0] == 1 and all(phase_distance(f, g) > 2 for g in donor) for f in other)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    rows, hashes, contexts = [], [], {}
    with ExitStack() as stack:
        for row, samples in read_archive(args.archive, 80):
            edge = row["edge"]
            if edge not in contexts:
                pilot = np.fromfile(args.assets / f"{edge}.f32", dtype="<f4")
                receiver = Receiver(args.binary, pilot)
                stack.callback(receiver.close)
                contexts[edge] = receiver
            target, acquisition = row["target"], row["acquisition"]
            mid = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
            rows.append(tuple(contexts[edge].timed(samples, lane, mid)[0] for lane in (0, 1)))
            hashes.append(row["sha256"])
    print(json.dumps(dict(visits=len(rows), input_sha256=digest(json.dumps(hashes).encode()),
                          receiver_sha256=digest(args.binary.read_bytes()), **audit(rows)), indent=2))


if __name__ == "__main__":
    main()
