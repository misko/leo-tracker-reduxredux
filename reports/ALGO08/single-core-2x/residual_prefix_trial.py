"""Compare the frozen conditional schedule on one 192-visit sealed prefix."""

import argparse
import json
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path

import numpy as np
from residual_native_trial import ScheduledReceiver, bytes_fields, time_pair

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastScanStore, FastSegmentSource, safe_id
from tools.algo08_scan import PINS
from tools.pipeline_eval.qualification.full_v5_check import _probe
from tools.pipeline_eval.variants.experimental import residual_schedule
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.receiver_residual_build import (
    FRACTIONAL_BATCH_SHA256,
)

VISITS = 192
SCHEDULE_SHA256 = "1261e213195c906854ea13b5562e838990a78a04768906e6d0319e772e345eda"
PROFILE_CONTROL_SHA256 = "b64fef8c2cb0b473b0f3f7e6d7a6b08cca1543293a936ba848997f84c77675dd"


def public_segment(panel, name):
    recordings = {safe_id(job["recording"]) for job in json.loads(panel.read_bytes())["jobs"]}
    if name not in recordings:
        raise ValueError("Expected one of the frozen public recordings")
    store = FastScanStore(panel.parent)
    _, _, inventory = store.inventory(panel.parent / name, verify_windows=False)
    return inventory["segments"][0]


def physical_segment(binding, bulk):
    case = json.loads(binding.read_bytes())["case"]
    entry = case["recording"]["segments"][0]
    return case["id"], dict(path=(bulk / entry["path"]).parent,
                            manifest_digest="sha256:" + entry["sha256"])


def sealed_prefix(segment):
    source = FastSegmentSource(segment, stop_sequence=VISITS)
    lanes = tuple(source.receiver_ids)
    if lanes != (0, 1) or source.reader.manifest.sample_rate_hz != 10_000_000:
        raise ValueError("Expected two ordered native-rate physical receiver lanes")
    policy = FastScanPolicyV2()
    rows, scheduled, excluded = [], [], []
    with compressed_input_buffer():
        for window in source.windows():
            acquisition, target = window.acquisition, window.target
            visit = acquisition["global_visit"]
            if visit != len(scheduled):
                raise ValueError("Expected complete chronological prefix from visit zero")
            scheduled.append((visit, window.iq_sha256))
            if not valid_window_support(
                acquisition, window.sample_rate_hz, window.samples.shape, lanes, policy,
            ):
                excluded.append(visit)
                continue
            center = (target["rf_center_hz"] - target["lnb_lo_hz"]
                      - acquisition["actual_if_center_hz"])
            samples = np.ascontiguousarray(window.samples)
            for lane in lanes:
                row = _probe(window, lane, [])
                del row["candidates"]
                rows.append((row, center, samples))
    if len(scheduled) != VISITS or len(rows) != 2 * (VISITS - len(excluded)):
        raise ValueError("Incomplete scheduled prefix or missing lane")
    return rows, excluded, canonical_digest(scheduled)


def observe(control, candidate, asset, rows):
    """Validate both new entries on every admitted lane before timing."""
    measured = []
    with ExitStack() as stack:
        reference = Receiver(control, asset)
        stack.callback(reference.close)
        experiment = ScheduledReceiver(candidate, asset)
        stack.callback(experiment.close)
        for row, center, samples in rows:
            lane = row["receiver_id"]
            full, _, _ = reference.timed(samples, lane, center)
            scheduled, _, _ = experiment.timed(samples, lane, center)
            primary, _, _ = experiment.timed_primary(samples, lane, center)
            if bytes_fields(full) != bytes_fields(scheduled):
                raise ValueError("Optional entry changed a full two-scan factor")
            if bytes_fields(primary) != bytes_fields(f for f in full if f[0] == 0):
                raise ValueError("Optional entry changed a primary factor")
            measured.append((row, center, samples, full))
    return measured


def run_trial(args):
    if args.physical_binding:
        case, segment = physical_segment(args.physical_binding, args.bulk)
    else:
        case = args.public_recording
        segment = public_segment(args.panel, case)

    digests = {name: sha256(getattr(args, name).read_bytes()).hexdigest()
               for name in ("control", "candidate", "profile_control", "profile_candidate")}
    if digests["control"] != FRACTIONAL_BATCH_SHA256:
        raise ValueError("Expected the frozen full-support fractional batch control")
    if digests["profile_control"] != PROFILE_CONTROL_SHA256:
        raise ValueError("Expected the corresponding frozen fractional batch profile control")
    if sha256(Path(residual_schedule.__file__).read_bytes()).hexdigest() != SCHEDULE_SHA256:
        raise ValueError("The frozen residual schedule changed")

    rows, excluded, scheduled_sha256 = sealed_prefix(segment)
    edge, = {row["edge"] for row, _, _ in rows}
    asset_path = args.assets / f"{edge}.f32"
    asset = asset_path.read_bytes()
    if sha256(asset).hexdigest() != PINS[asset_path.name]:
        raise ValueError("The original pilot reference changed")
    template = np.frombuffer(asset, dtype="<f4")
    prefix = observe(args.control, args.candidate, template, rows)
    repeats = [
        time_pair(args.control, args.candidate, template, prefix, candidate_first=first, audit=True)
        for first in (True, False)
    ]
    profiled = time_pair(
        args.profile_control, args.profile_candidate, template, prefix,
        candidate_first=False, audit=True,
    )
    for repeat in (*repeats[1:], profiled):
        for key in ("selections_sha256", "lane_counts", "observed_rank_orders",
                    "changed_factor_orders", "schedule_reasons"):
            if repeat[key] != repeats[0][key]:
                raise ValueError(f"Arm order or instrumentation changed {key}")
    counts = {}
    for mode, profile in profiled["profiles"].items():
        if profile is None:
            raise ValueError("Expected an instrumented receiver for native call counts")
        lanes = profile["measure"]["calls"]
        residuals = profile["timing"]["calls"] - lanes
        if lanes != len(prefix) or residuals != profile["cancel"]["calls"]:
            raise ValueError("Native scout and cancellation clocks disagree")
        counts[mode] = dict(factor_calls=lanes, primary_scouts=lanes, residual_scouts=residuals)
    return dict(
        case=case, scheduled_visits=VISITS, excluded_visit_indices=excluded,
        admitted_lane_count=len(prefix), ordered_window_digest=scheduled_sha256,
        segment_manifest_digest=segment["manifest_digest"], edge=edge,
        pilot_sha256=PINS[asset_path.name], schedule_sha256=SCHEDULE_SHA256,
        binaries_sha256=digests,
        original_rank_one_only=sum(len(factors) == 1 and factors[0][0] == 1
                                   for _, _, _, factors in prefix),
        calls=counts, profile=profiled["profiles"], repeats=repeats,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "candidate", "profile_control", "profile_candidate", "assets"):
        parser.add_argument(name, type=Path)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--physical-binding", type=Path)
    inputs.add_argument("--public-recording")
    parser.add_argument("--bulk", type=Path, default=Path("/srv/bulk"))
    parser.add_argument("--panel", type=Path)
    args = parser.parse_args()
    if args.public_recording and not args.panel:
        parser.error("--public-recording requires --panel")
    print(json.dumps(run_trial(args), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
