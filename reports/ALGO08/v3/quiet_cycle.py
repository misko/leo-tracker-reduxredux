"""Replay a three-check quiet-cycle receiver schedule on pinned signed detector packets."""

from collections import defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path

from anchor_exposure import PINS, enroll, packet


HERE = Path(__file__).resolve().parent
CASES = ("DS30-0016", "DS30-0008", "north")
RAW_CLOCK = "56b4d57f4534091150621f7dba65cce1edba1d0fbe33238680e10516bf552c5e"
CHECKS = (0, 4, 8)
OPTIONAL = (1, 2, 3, 5, 6, 7)


def tally_interval(result, values, radios):
    """Charge every optional call unless this group passes all three checks."""
    result["tested_groups"] += 1
    if any(values[radio][slot] for radio in radios for slot in CHECKS):
        return
    calls = len(OPTIONAL) * len(radios)
    missed = sum(values[radio][slot] for radio in radios for slot in OPTIONAL)
    result["quiet_groups"] += 1
    result["skipped_calls"] += calls
    result["lost_positive_lanes"] += missed
    if missed:
        result["groups_with_loss"] += 1
    else:
        result["oracle_veto_skipped_calls"] += calls


def census(document):
    streams = defaultdict(lambda: [[], []])
    for _, sequence, radio, stream, _, events in enroll(document):
        values = streams[stream][radio]
        if sequence != len(values):
            raise ValueError("Nonconsecutive RF opportunity")
        values.append(events[1])
    counters = ("tested_groups", "quiet_groups", "skipped_calls", "groups_with_loss",
                "lost_positive_lanes", "oracle_veto_skipped_calls")
    results = {policy: dict.fromkeys(counters, 0) for policy in ("individual", "stereo")}
    short_lanes = 0
    short_positive = 0
    for lanes in streams.values():
        if len(lanes[0]) != len(lanes[1]):
            raise ValueError("Missing radio")
        for lane in lanes:
            short = [positive for slot, positive in enumerate(lane) if slot % 8]
            short_lanes += len(short)
            short_positive += sum(short)
        for start in range(0, len(lanes[0]) - 8, 8):
            values = [lane[start:start + 9] for lane in lanes]
            for radio in (0, 1):
                tally_interval(results["individual"], values, (radio,))
            tally_interval(results["stereo"], values, (0, 1))
    return dict(short_lanes=short_lanes, short_positive_lanes=short_positive,
                all_empty_short_lanes=short_lanes - short_positive, policies=results)


def compare():
    cases = {}
    for name in CASES:
        root, pin = PINS[name]["12ms"]
        cases[name] = dict(packet_sha256=pin, **census(packet(root, pin)))
    raw = (HERE / "measurements/unified-short-layout.json.gz").read_bytes()
    if sha256(raw).hexdigest() != RAW_CLOCK:
        raise ValueError("Weak clock receipt changed")
    weak = cases["DS30-0016"]
    bootstrap = json.loads(gzip.decompress(raw))["observations"]["weak"]["rows"]["candidate"]["science"]["bootstrap"]
    native = bootstrap["receiver_audit"]["native"]
    if (bootstrap["native_sha256"] != "sha256:" + weak["packet_sha256"]
            or native["native_calls"]["short_primary"] != weak["short_lanes"]
            or native["factors"]["short_primary"] != weak["short_positive_lanes"]):
        raise ValueError("Timing and occupancy must come from the same weak native packet")
    mean_s = native["native_cpu_ns"]["short_primary"] / 1e9 / weak["short_lanes"]
    acquisition_s = bootstrap["phases"]["authenticated_raw_acquisition"]["elapsed_s"]
    return dict(cases=cases, weak_short_cpu_s_per_call=mean_s, weak_acquisition_s=acquisition_s,
                weak_target_reduction_s=acquisition_s - 2.700, raw_clock_sha256=RAW_CLOCK,
                weak_projected_cpu_s={policy: {k: policy_counts[k] * mean_s for k in
                                      ("skipped_calls", "oracle_veto_skipped_calls")}
                                      for policy, policy_counts in weak["policies"].items()},
                weak_all_empty_short_cpu_s=weak["all_empty_short_lanes"] * mean_s)


if __name__ == "__main__":
    print(json.dumps(compare(), indent=2, sort_keys=True, allow_nan=False))
