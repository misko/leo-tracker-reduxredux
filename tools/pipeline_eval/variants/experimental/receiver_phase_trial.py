"""Compare frame-relative verification on small matched saved receiver slices."""

import argparse
import ctypes as ct
import json
from collections import Counter, defaultdict
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from ..carrier_continuation import Continuation
from .receiver_benchmark import Receiver, digest, read_archive, read_simulated_prefix


def phase_stats(binary):
    load = ct.CDLL(str(binary.resolve())).experimental_phase_free_stats
    load.argtypes = [ct.POINTER(ct.c_uint64), ct.c_int]
    load.restype = None
    values = (ct.c_uint64 * 3)()
    load(values, 1)
    return dict(attempted=values[0], accepted=values[1], fallback=values[0] - values[1],
                margin_order_retries=values[2])


def compare(rows, binaries, assets):
    with ExitStack() as resources:
        receivers = {}
        for edge in sorted({row["edge"] for row, _ in rows}):
            asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            receivers[edge] = [Receiver(binary, asset) for binary in binaries]
            for receiver in receivers[edge]:
                resources.callback(receiver.close)
        runs, differences = [], []
        for repeat in range(2):
            phase_stats(binaries[1])
            histories = defaultdict(Continuation)
            cpu, counts, max_score = [0, 0], Counter(), [0., 0.]
            for index, (row, iq) in enumerate(rows):
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                for lane in (0, 1):
                    factors, selections = [None, None], [None, None]
                    first = (index + lane + repeat) % 2
                    for arm in (first, 1 - first):
                        detector = receivers[row["edge"]][arm]
                        factors[arm], elapsed, _ = detector.timed(iq, lane, center)
                        cpu[arm] += elapsed
                        probe = dict(
                            receiver_id=lane, channel=target["channel"],
                            actual_rf_hz=acq["actual_if_center_hz"] + target["lnb_lo_hz"],
                            valid_start_counter=acq["sample_start"],
                            candidates=[detector.criteria(*factor) for factor in factors[arm]],
                        )
                        selections[arm] = histories[(row["case"], arm)].select(probe)
                    original, candidate = factors
                    counts["factors"] += len(original)
                    counts["second_factors"] += sum(p[0] == 1 for p in original)
                    counts["changed_scores_or_factors"] += original != candidate
                    counts["changed_continuation"] += selections[0] != selections[1]
                    counts["selected"] += selections[0][1] is not None
                    counts["changed_strong_margin"] += (
                        tuple(f[4] - f[5] >= .1 for f in original)
                        != tuple(f[4] - f[5] >= .1 for f in candidate)
                    )
                    if tuple(p[:4] for p in original) != tuple(p[:4] for p in candidate):
                        counts["changed_carrier_identity_or_measurement"] += 1
                        if not repeat:
                            differences.append(dict(key=row["key"], lane=lane, factors=factors))
                    else:
                        for old, new in zip(original, candidate, strict=True):
                            for i, (a, b) in enumerate(zip(old[4:], new[4:], strict=True)):
                                max_score[i] = max(max_score[i], abs(a - b))
            stats = phase_stats(binaries[1])
            runs.append(dict(cpu_s=[ns / 1e9 for ns in cpu], counts=counts,
                             max_exact_control_score_delta=max_score, phase=stats))
        if runs[0]["counts"] != runs[1]["counts"] or runs[0]["phase"] != runs[1]["phase"]:
            raise ValueError("repeated fractional evidence comparison differs")
        return dict(lanes=2 * len(rows), runs=runs, carrier_differences=differences,
                    iq_sha256=digest(json.dumps([row["sha256"] for row, _ in rows]).encode()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("prospective", type=Path)
    parser.add_argument("weak", type=Path)
    parser.add_argument("simulation_panel", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    slices = {"physical": list(read_archive(args.prospective, 80)),
              "weak": list(read_archive(args.weak, 18))}
    simulated = defaultdict(list)
    for row, iq in read_simulated_prefix(args.simulation_panel, 40):
        simulated[row["case"]].append((row, iq))
    slices.update(simulated)
    binaries = args.reference, args.candidate
    cohorts = {key: compare(rows, binaries, args.assets) for key, rows in slices.items()}
    print(json.dumps(dict(binaries=[digest(p.read_bytes()) for p in binaries],
                          cohorts=cohorts), indent=2))


if __name__ == "__main__":
    main()
