"""Compare the corrected, packed and deployed receivers on the same saved lanes."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from itertools import permutations
import json
from pathlib import Path
from statistics import median
from struct import Struct

import numpy as np

from receiver_refine_parity_trial import austin_windows
from tools.algo08_scan import PINS
from tools.pipeline_eval.qualification import austin_waveform as wave
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest, read_archive


SHA256 = {
    "deployed": "f37673f081cd0e8278695d72a51127219c0a6345c93ff43bac898348565fd809",
    "packed": "88b4f3ba6479b287cd581c604afa796992a2e6c7cbd34761d176f24500123f03",
    "restored": "6f2cc95d835ffcff8226a925dddca9d5b03d8fe6b06c159b165ac0807b805a91",
}
FACTOR = Struct("<ii4d")
FIELDS = ("rank", "integer_epoch", "fractional_epoch", "signed_cfo_hz", "exact_score", "control_score")
WEAK_IQ_SHA256 = "d3005a6496d2ca650ad9853bd5f307332ec79b53f976193a5efec9f31ca106e5"
COMPARISONS = (("packed", "restored"), ("deployed", "restored"), ("deployed", "packed"))


def inputs(weak, archive, source_audit, wide_reference):
    groups = defaultdict(list)
    visits = list(read_archive(weak, 18))
    ordered_authority = json.dumps([row["sha256"] for row, _ in visits]).encode()
    if len(visits) != 18 or digest(ordered_authority) != WEAK_IQ_SHA256:
        raise ValueError("The comparison requires the saved 18-window weak archive")
    for row, samples in visits:
        acquisition, target = row["acquisition"], row["target"]
        actual = acquisition["actual_if_center_hz"] + target["lnb_lo_hz"]
        center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
        for lane in (0, 1):
            meta = dict(receiver_id=lane, channel=target["channel"], actual_rf_hz=actual,
                        valid_start_counter=acquisition["sample_start"])
            groups["ds26-weak"].append((row["case"], row["key"], row["edge"], center,
                                        row["sha256"], meta, samples))
    for panel, edge, start, authority, samples in austin_windows(archive, source_audit, wide_reference):
        meta = dict(receiver_id=0, channel=0, actual_rf_hz=wave.EDGE_HZ[edge],
                    valid_start_counter=start * wave.RATE // 1000)
        fallback = -50_000. if edge == "lower" else 50_000.
        for configuration, center in (("zero", 0.), ("offset", fallback)):
            group = f"austin-{panel}-{configuration}"
            groups[group].append((group, f"{edge}:{start}", edge, center, authority, meta, samples))
    return groups


def factor_bytes(factors):
    return b"".join(FACTOR.pack(*factor) for factor in factors)


def compare(rows, reference, candidate):
    counts = Counter()
    maximum = {field: 0. for field in FIELDS[1:]}
    changed_cfo = []
    for row in rows:
        left, right = (row["arms"][arm] for arm in (reference, candidate))
        first, second = left["factors"], right["factors"]
        ranks_left, ranks_right = tuple(f[0] for f in first), tuple(f[0] for f in second)
        counts["lanes_changed"] += factor_bytes(first) != factor_bytes(second)
        counts["rank_order_changed"] += ranks_left != ranks_right
        counts["continuation_changed"] += left["continuation"] != right["continuation"]
        old, new = {f[0]: f for f in first}, {f[0]: f for f in second}
        counts["removed_factors"] += len(old.keys() - new.keys())
        counts["added_factors"] += len(new.keys() - old.keys())
        for rank in sorted(old.keys() & new.keys()):
            for index, field in enumerate(FIELDS[1:], start=1):
                a, b = old[rank][index], new[rank][index]
                encoded = "<i" if field == "integer_epoch" else "<d"
                if Struct(encoded).pack(a) == Struct(encoded).pack(b):
                    continue
                counts[field] += 1
                maximum[field] = max(maximum[field], abs(a - b))
                if field == "signed_cfo_hz":
                    changed_cfo.append(dict(key=row["key"], lane=row["receiver_id"], rank=rank,
                                            before_hz=a, after_hz=b, delta_hz=b - a))
    return dict(counts=counts, maximum_absolute_delta=maximum, changed_cfo=changed_cfo)


def measure(group, radios, arms=tuple(SHA256), comparisons=COMPARISONS, cycles=2):
    orders = tuple(permutations(arms))
    all_times = []
    canonical = None
    for repeat in range(cycles * len(orders)):
        elapsed = dict.fromkeys(arms, 0)
        histories = {arm: defaultdict(Continuation) for arm in arms}
        measured = []
        for index, (case, key, edge, center, authority, meta, samples) in enumerate(group):
            readouts = {}
            for arm in orders[(index + repeat) % len(orders)]:
                radio = radios[edge, arm]
                factors, cpu, _ = radio.timed(samples, meta["receiver_id"], center)
                continuation = histories[arm][case].select(
                    dict(meta, candidates=[radio.criteria(*factor) for factor in factors]),
                )
                readouts[arm] = dict(factors=factors, factor_sha256=digest(factor_bytes(factors)),
                                     continuation=continuation)
                elapsed[arm] += cpu
            measured.append(dict(key=key, edge=edge, center_hz=center, iq_sha256=authority,
                                 receiver_id=meta["receiver_id"], arms=readouts))
        if canonical is None:
            canonical = measured
        elif canonical != measured:
            raise ValueError("A native factor or continuation result changed between repeats")
        all_times.append(elapsed)
    return dict(
        lane_configurations=len(group), cpu_ns=all_times, rows=canonical,
        median_cpu_ns={arm: median(t[arm] for t in all_times) for arm in arms},
        paired={f"{a}_to_{b}": dict(compare(canonical, a, b),
                                   median_cpu_change=median(t[b] / t[a] - 1 for t in all_times),
                                   median_delta_cpu_ns=median(t[b] - t[a] for t in all_times))
                for a, b in comparisons},
    )


def trial(bench, assets, weak, archive, source_audit, wide_reference):
    paths = dict(deployed=assets / "cancellation-factors.so",
                 packed=bench / "c803-packed-cancel-trial-v2/candidate/use.so",
                 restored=bench / "receiver-cfo-lineage-fix/restored.so")
    if {arm: digest(path.read_bytes()) for arm, path in paths.items()} != SHA256:
        raise ValueError("Expected the three pinned comparison binaries")
    groups = inputs(weak, archive, source_audit, wide_reference)
    with ExitStack() as stack:
        radios = {}
        for edge in wave.EDGE_HZ:
            asset = assets / f"{edge}.f32"
            if digest(asset.read_bytes()) != PINS[asset.name]:
                raise ValueError("The pilot template differs from the release pin")
            template = np.fromfile(asset, dtype="<f4")
            for arm, path in paths.items():
                receiver = Receiver(path, template)
                stack.callback(receiver.close)
                radios[edge, arm] = receiver
        return dict(binaries=SHA256, samples={name: measure(group, radios) for name, group in groups.items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bench", "assets", "weak", "archive", "source_audit", "wide_reference"):
        parser.add_argument(name, type=Path)
    print(json.dumps(trial(**vars(parser.parse_args())), allow_nan=False, indent=2))
