"""Check the Q15 scout on the fixed physical, weak and two simulated slices."""

import argparse
import json
from collections import Counter
from contextlib import ExitStack
from itertools import chain, groupby
from pathlib import Path
from struct import pack

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import (
    Receiver, benchmark, digest, read_archive, read_simulated_prefix,
)
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical


def rank_changes(binaries, rows, assets):
    counts = Counter()
    with ExitStack() as closers:
        receivers = {}
        for edge in {row["edge"] for row, _ in rows}:
            asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            for arm, binary in enumerate(binaries):
                receiver = Receiver(binary, asset)
                receivers[edge, arm] = receiver
                closers.callback(receiver.close)
        for row, samples in rows:
            target, acq = row["target"], row["acquisition"]
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            for lane in (0, 1):
                reference, candidate = [receivers[row["edge"], arm].timed(samples, lane, center)[0]
                                        for arm in (0, 1)]
                old, new = ({factor[0]: factor for factor in factors}
                            for factors in (reference, candidate))
                for rank in (0, 1):
                    if rank in old and rank not in new:
                        counts[rank, "lost"] += 1
                    elif rank in new and rank not in old:
                        counts[rank, "gained"] += 1
                    elif rank in old and old[rank] != new[rank]:
                        change = "integer_epoch_changed" if old[rank][1] != new[rank][1] else "values_changed"
                        counts[rank, change] += 1
                if len(old) == len(new) == 2 and reference[0][0] != candidate[0][0]:
                    counts["both", "reordered"] += 1
    return {f"{rank}:{change}": count for (rank, change), count in sorted(counts.items(), key=str)}


def evaluate(binaries, rows, assets):
    return dict(
        input_sha256=digest(json.dumps([row for row, _ in rows], sort_keys=True).encode()),
        edges=dict(Counter(row["edge"] for row, _ in rows)),
        mixer_centers_hz=dict(Counter(
            row["target"]["rf_center_hz"] - row["target"]["lnb_lo_hz"]
            - row["acquisition"]["actual_if_center_hz"] for row, _ in rows
        )),
        timing=benchmark(binaries, rows, assets, repeats=3),
        factors_by_rank=rank_changes(binaries, rows, assets),
    )


def run(oracle, candidate, oracle_profile, candidate_profile, assets, physical, weak, panel):
    binaries = (oracle, candidate)
    instrumented = (oracle_profile, candidate_profile)
    samples = chain(
        (("physical", read_archive(physical, 80)), ("weak", read_archive(weak, 18))),
        groupby(read_simulated_prefix(panel, 40), key=lambda item: item[0]["case"]),
    )
    out = dict(
        timing_binaries_sha256=[digest(path.read_bytes()) for path in binaries],
        profile_binaries_sha256=[digest(path.read_bytes()) for path in instrumented],
    )
    for label, rows in samples:
        rows = list(rows)
        out[label] = evaluate(binaries, rows, assets)
        if label == "physical":
            out[label]["profile"] = benchmark(instrumented, rows, assets, repeats=2)
    return out


def dual_entry(binaries, rows, assets, symbol):
    times = [[0, 0] for _ in range(3)]
    reference_counts = Counter()
    mismatches = set()
    with ExitStack() as closers:
        receivers = {}
        for edge in {row["edge"] for row, _ in rows}:
            asset = np.fromfile(assets / f"{edge}.f32", dtype="<f4")
            for arm, binary in enumerate(binaries):
                receiver = Receiver(binary, asset)
                closers.callback(receiver.close)
                entry = getattr(receiver.lib, symbol)
                entry.argtypes, entry.restype = receiver.run.argtypes, receiver.run.restype
                receiver.run = entry
                receivers[edge, arm] = receiver
        for repeat, arm_times in enumerate(times):
            for index, (row, samples) in enumerate(rows):
                target, acq = row["target"], row["acquisition"]
                center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
                for lane in (0, 1):
                    observations = {}
                    first = (repeat + index + lane) % 2
                    for arm in (first, 1 - first):
                        factors, cpu, _ = receivers[row["edge"], arm].timed(samples, lane, center)
                        arm_times[arm] += cpu
                        observations[arm] = b"".join(pack("<ii4d", *factor) for factor in factors)
                        if repeat == arm == 0:
                            reference_counts.update(factor[0] for factor in factors)
                    if observations[0] != observations[1]:
                        mismatches.add((row["key"], lane))
    return dict(cpu_s=[[value / 1e9 for value in repeat] for repeat in times],
                reference_counts=reference_counts, different_lanes=sorted(mismatches))


def chronological(oracle, candidate, dual_oracle, dual_candidate, assets, binding):
    rows = list(read_physical(binding, Path("/srv/bulk"), 128))
    dual = (dual_oracle, dual_candidate)
    return dict(
        standalone=evaluate((oracle, candidate), rows, assets),
        timing_binaries_sha256=[digest(path.read_bytes()) for path in (oracle, candidate)],
        dual_binaries_sha256=[digest(path.read_bytes()) for path in dual],
        dual_entries={symbol: dual_entry(dual, rows, assets, symbol)
                      for symbol in ("cancellation_factors", "cancellation_primary_factors")},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    archive = modes.add_parser("archives")
    for name in ("oracle", "candidate", "oracle_profile", "candidate_profile", "assets", "physical", "weak",
                 "panel"):
        archive.add_argument(name, type=Path)
    prefix = modes.add_parser("chronological")
    for name in ("oracle", "candidate", "dual_oracle", "dual_candidate", "assets", "binding"):
        prefix.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    handler = run if args.pop("mode") == "archives" else chronological
    print(json.dumps(handler(**args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
