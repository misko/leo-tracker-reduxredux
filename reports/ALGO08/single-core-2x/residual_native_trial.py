"""Time the original and conditional residual receiver on the same sealed prefix."""

import argparse
from collections import Counter
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
from struct import pack

import numpy as np

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastSegmentSource
from residual_schedule_trial import changes, read
from tools.algo08_scan import PINS
from tools.pipeline_eval.qualification.full_v5_check import _probe, factor_candidate
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.receiver_residual_build import PACKED_SHA256
from tools.pipeline_eval.variants.experimental.residual_schedule import Replay


class ScheduledReceiver(Receiver):
    def __init__(self, binary, asset):
        super().__init__(binary, asset)
        self.primary = self.lib.cancellation_primary_factors
        self.primary.argtypes, self.primary.restype = self.run.argtypes, self.run.restype

    def timed_primary(self, samples, lane, center):
        original, self.run = self.run, self.primary
        try:
            return self.timed(samples, lane, center)
        finally:
            self.run = original


def tuple_fields(records):
    return tuple((f["candidate_rank"], f["integer_epoch_sample"], f["fractional_epoch_offset_samples"],
                  f["fractional_tracking_cfo_hz"], f["fractional_exact_score"],
                  f["fractional_control_score"]) for f in records)


def bytes_fields(values):
    return b"".join(pack("<ii4d", *record) for record in values)


def candidates(factors):
    return [factor_candidate(rank, epoch, status="complete", offset=offset, cfo=hz,
                             exact=exact, control=control, margin=exact-control)
            for rank, epoch, offset, hz, exact, control in factors]


def load_prefix(inventory_path, ledger, visits):
    inventory = json.loads(inventory_path.read_bytes())
    if canonical_digest(inventory) != ledger["input_manifest_sha256"]:
        raise ValueError("Sealed inventory differs from the saved factor ledger")
    expected = {row["visit_index"]: {} for row in ledger["rows"] if row["visit_index"] < visits}
    for row in ledger["rows"]:
        if row["visit_index"] in expected:
            expected[row["visit_index"]][row["receiver_id"]] = row
    excluded = {row["visit"]: row for row in ledger["excluded_windows"] if row["visit"] < visits}
    source = FastSegmentSource(inventory["segments"][0], stop_sequence=visits)
    policy = FastScanPolicyV2()
    if tuple(source.receiver_ids) != (0, 1) or source.reader.manifest.sample_rate_hz != 10_000_000:
        raise ValueError("Expected sealed stereo native-rate input")
    windows = []
    seen = 0
    with compressed_input_buffer():
        for window in source.windows():
            acq = window.acquisition
            index = acq["global_visit"]
            if index != seen:
                raise ValueError("Nonchronological prefix")
            seen += 1
            if not valid_window_support(acq, window.sample_rate_hz, window.samples.shape, (0, 1), policy):
                if index not in excluded or excluded[index]["iq_sha256"] != window.iq_sha256:
                    raise ValueError("Excluded sealed window differs from the ledger")
                continue
            target = window.target
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acq["actual_if_center_hz"]
            samples = np.ascontiguousarray(window.samples)
            for lane in (0, 1):
                row = expected[index][lane]
                metadata = _probe(window, lane, [])
                del metadata["candidates"]
                if metadata != {k: v for k, v in row.items() if k != "candidates"}:
                    raise ValueError("Sealed RF lane differs from the original ledger")
                windows.append((metadata, center, samples, tuple_fields(row["candidates"])))
    if seen != visits or len(windows) != 2 * len(expected):
        raise ValueError("Incomplete measured prefix")
    return windows, len(excluded)


def validation(binary, asset, windows):
    receiver = ScheduledReceiver(binary, asset)
    try:
        for metadata, center, samples, full in windows:
            primary = tuple(f for f in full if f[0] == 0)
            actual, _, _ = receiver.timed_primary(samples, metadata["receiver_id"], center)
            if bytes_fields(primary) != bytes_fields(actual):
                raise ValueError(f"Native raw-only entry changed rank zero at {metadata}")
    finally:
        receiver.close()
    return dict(lanes=len(windows), rank_one_only=sum(
        len(full) == 1 and full[0][0] == 1 for _, _, _, full in windows))


def time_pair(control, candidate, asset, windows, *, candidate_first, audit=False):
    modes = ("conditional", "always-two") if candidate_first else ("always-two", "conditional")
    policies = {mode: Replay(mode) for mode in modes}
    cpu = {mode: Counter() for mode in modes}
    selected = {mode: [] for mode in modes}
    observed_orders = {mode: Counter() for mode in modes}
    changed_order = []
    counts = Counter()
    with ExitStack() as stack:
        original = Receiver(control, asset)
        stack.callback(original.close)
        scheduled = ScheduledReceiver(candidate, asset)
        stack.callback(scheduled.close)
        if audit:
            original.reset_profile()
            scheduled.reset_profile()
        for metadata, center, samples, full in windows:
            calls = {}
            orders = {}
            lane = metadata["receiver_id"]
            for mode in modes:
                def measure(residual):
                    if mode == "always-two":
                        receiver = original.timed
                    else:
                        receiver = scheduled.timed if residual else scheduled.timed_primary
                    factors, elapsed, _ = receiver(samples, lane, center)
                    expected = full if residual else tuple(f for f in full if f[0] == 0)
                    if bytes_fields(factors) != bytes_fields(expected):
                        raise ValueError(f"{mode} disagrees with frozen original factors at {metadata}")
                    calls[mode] = elapsed
                    return candidates(factors)

                residual, observed, admitted = policies[mode].visit(metadata, measure)
                selected[mode].append(dict(metadata, candidates=admitted))
                if audit:
                    order = tuple(f["candidate_rank"] for f in observed)
                    orders[mode] = order
                    observed_orders[mode][",".join(map(str, order)) or "empty"] += 1
                if mode == "conditional":
                    scheduled_residual = residual
            group = "residual_requested" if scheduled_residual else "residual_skipped"
            counts[group] += 1
            for mode, elapsed in calls.items():
                cpu[mode][group] += elapsed
            if audit and orders["always-two"] != orders["conditional"]:
                changed_order.append(dict(visit=metadata["visit_index"], receiver=lane,
                                          before=orders["always-two"], after=orders["conditional"]))
        profiles = (original.profile(), scheduled.profile()) if audit else None
    difference, rows = changes(selected["always-two"], selected["conditional"])
    result = dict(first=modes[0], lane_counts=counts,
                  native_cpu_s={mode: {k: t / 1e9 for k, t in times.items()}
                                for mode, times in cpu.items()},
                  selection_changes=difference, changed_rows=rows,
                  selections_sha256={mode: canonical_digest(values) for mode, values in selected.items()},
                  selections={mode: sum(bool(row["candidates"]) for row in values)
                              for mode, values in selected.items()})
    if audit:
        selected_ranks, first_selected = {}, {}
        for mode, values in selected.items():
            kept = [row for row in values if row["candidates"]]
            selected_ranks[mode] = Counter(row["candidates"][0]["candidate_rank"] for row in kept)
            first_selected[mode] = kept[0]["visit_index"] if kept else None
        result.update(
            profiles=dict(zip(("always-two", "conditional"), profiles, strict=True)),
            schedule_reasons={mode: policy.reasons for mode, policy in policies.items()},
            observed_rank_orders=observed_orders, changed_factor_orders=changed_order,
            selected_ranks=selected_ranks, first_selected_visit=first_selected,
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ledger", "detections", "inventory", "control", "candidate", "assets"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--visits", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.visits <= 128:
        parser.error("Timing requires a prefix of 1 to 128 visits")
    if sha256(args.control.read_bytes()).hexdigest() != PACKED_SHA256:
        raise ValueError("The reference must be frozen packed 950c")
    ledger_digest, ledger, native = read(args.ledger, args.detections)
    prefix, exclusions = load_prefix(args.inventory, ledger, args.visits)
    edges = {metadata["edge"] for metadata, _, _, _ in prefix}
    edge, = edges
    asset_path = args.assets / f"{edge}.f32"
    if sha256(asset_path.read_bytes()).hexdigest() != PINS[asset_path.name]:
        raise ValueError("The original pilot asset changed")
    asset = np.fromfile(asset_path, dtype="<f4")
    checked = validation(args.candidate, asset, prefix)
    full_sha = canonical_digest([row for row in native["source"]["probes"]
                                 if row["visit_index"] < args.visits])
    repeats = [time_pair(args.control, args.candidate, asset, prefix, candidate_first=i == 0)
               for i in range(2)]
    if any(row["selections_sha256"]["always-two"] != full_sha for row in repeats):
        raise ValueError("The chronological control failed to replay the original prefix")
    if repeats[0]["selections_sha256"] != repeats[1]["selections_sha256"]:
        raise ValueError("Arm order changed selections")
    print(json.dumps(dict(ledger_sha256=ledger_digest, frozen_detector_sha256=PACKED_SHA256,
                          candidate_sha256=sha256(args.candidate.read_bytes()).hexdigest(),
                          pilot_sha256=PINS[asset_path.name], requested_visits=args.visits,
                          excluded_visits=exclusions, validation=checked, repeats=repeats), allow_nan=False))


if __name__ == "__main__":
    main()
