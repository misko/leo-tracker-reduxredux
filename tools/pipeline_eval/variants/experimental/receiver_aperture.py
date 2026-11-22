"""Measure the half-window nomination scout on bounded physical and simulated I/Q."""

import argparse
import json
from collections import Counter, defaultdict
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from ..carrier_continuation import Continuation
from .receiver_benchmark import Receiver, digest, read_archive, read_simulated_prefix
from .receiver_tracking import agree


def compare(reference, candidate, counts):
    counts["changed_lanes"] += reference != candidate
    counts["reference_factors"] += len(reference)
    counts["candidate_factors"] += len(candidate)
    remaining = list(candidate)
    for i, factor in enumerate(reference):
        tags = ["factor"]
        if factor[0] == 1:
            tags.append("second_scan")
        if len(reference) == 2 and i == 1:
            tags.append("lower_margin")
        counts.update(f"reference_{tag}" for tag in tags if tag != "factor")
        match = next((p for p in remaining if agree(factor, p)), None)
        if match is None:
            counts.update(f"missed_{tag}" for tag in tags)
        else:
            remaining.remove(match)
    counts["extra_factors"] += len(remaining)
    counts["extra_second_scan"] += sum(p[0] == 1 for p in remaining)
    counts["extra_lower_margin"] += bool(len(candidate) == 2 and candidate[1] in remaining)


def trial(rows, binaries, assets):
    evidence = []
    with ExitStack() as stack:
        receivers = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            pilot = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            receivers[edge] = [Receiver(path, pilot) for path in binaries]
            for receiver in receivers[edge]:
                stack.callback(receiver.close)
        repeats = []
        for repeat in range(2):
            cpu = [0, 0]
            counts = Counter()
            history = defaultdict(Continuation)
            for i, (row, samples) in enumerate(rows):
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                for lane in (0, 1):
                    factors, picked = [None, None], [None, None]
                    first = (i + lane + repeat) % 2
                    for arm in (first, 1 - first):
                        receiver = receivers[row["edge"]][arm]
                        factors[arm], ticks, _ = receiver.timed(samples, lane, center)
                        cpu[arm] += ticks
                        probe = dict(receiver_id=lane, channel=target["channel"],
                                     actual_rf_hz=acq["actual_if_center_hz"] + target["lnb_lo_hz"],
                                     valid_start_counter=acq["sample_start"],
                                     candidates=[receiver.criteria(*p) for p in factors[arm]])
                        _, keep, _ = history[(row["case"], arm)].select(probe)
                        picked[arm] = None if keep is None else factors[arm][keep]
                    compare(*factors, counts)
                    old, new = picked
                    counts["reference_selected"] += old is not None
                    counts["candidate_selected"] += new is not None
                    counts["missed_selected"] += old is not None and (new is None or not agree(old, new))
                    counts["extra_selected"] += old is None and new is not None
                    if not repeat and factors[0] != factors[1]:
                        evidence.append(dict(key=row["key"], lane=lane, frozen=factors[0], shortened=factors[1]))
            repeats.append(dict(reference_cpu_s=cpu[0] / 1e9, short_cpu_s=cpu[1] / 1e9, counts=counts))
        if repeats[0]["counts"] != repeats[1]["counts"]:
            raise ValueError("aperture comparisons changed across repeats")
    return dict(visits=len(rows), lanes=2 * len(rows), runs=repeats, changed=evidence,
                iq_sha256=digest(json.dumps([row["sha256"] for row, _ in rows]).encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exact", type=Path)
    parser.add_argument("short", type=Path)
    parser.add_argument("prospective", type=Path)
    parser.add_argument("weak", type=Path)
    parser.add_argument("simulation_panel", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    inputs = {"prospective": list(read_archive(args.prospective, 16)),
              "weak": list(read_archive(args.weak, 18))}
    simulators = defaultdict(list)
    for row, samples in read_simulated_prefix(args.simulation_panel, 40):
        simulators[row["case"]].append((row, samples))
    inputs.update(simulators)
    bins = args.exact, args.short
    groups = {key: trial(rows, bins, args.assets) for key, rows in inputs.items()}
    print(json.dumps(dict(binaries=[digest(p.read_bytes()) for p in bins], cohorts=groups), indent=2))


if __name__ == "__main__":
    main()
