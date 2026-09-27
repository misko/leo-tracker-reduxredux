#!/usr/bin/env python3
"""Dev-only causal replay of 1 s and 5 s blind-search cadences."""

from __future__ import annotations

import argparse
import ctypes as ct
import hashlib
import json
import platform
import signal
import sys
import time
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from statistics import median

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT), str(ROOT / "native")]

from known_state_v3 import NativeKnownStateV3, build_library_v3  # noqa: E402
from replay import blind_observation, fast_observation  # noqa: E402
from tools.presence_dwell import NativeDwell, unpack  # noqa: E402
from tracking import Key, Policy, Tracker, reference_match  # noqa: E402


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CadenceSchedule:
    """Source-counter schedule with independent state for every tracker key."""

    def __init__(self, interval_seconds):
        if not np.isfinite(interval_seconds) or interval_seconds <= 0:
            raise ValueError("positive finite cadence required")
        self.interval_seconds = float(interval_seconds)
        self.last_blind = {}

    def begin(self, key, start_counter):
        previous = self.last_blind.get(key)
        due = previous is None or start_counter - previous >= self.interval_seconds * key.rate_hz
        if due:
            self.last_blind[key] = start_counter
        if not due:
            return False, "not_due"
        return True, "cold_blind" if previous is None else "scheduled_blind"


def timed(function, repetitions):
    expected, _ = function()
    measurements = []
    detail = None
    for _ in range(repetitions):
        cpu = time.process_time_ns()
        wall = time.perf_counter_ns()
        actual, detail = function()
        measurements.append({
            "cpu_ms": (time.process_time_ns() - cpu) / 1e6,
            "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
        })
        if actual != expected:
            raise ValueError("DSP observation changed across repetitions")
    return expected, detail, measurements


def classify_reference(reference_positive, matched, result_kind):
    if not reference_positive:
        return "not_reference_positive"
    if matched:
        return "covered"
    if result_kind == "unknown":
        return "unknown"
    return "lost"


def latency_rows(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["key_id"], []).append(row)
    output = []
    for key_id, values in sorted(grouped.items()):
        values.sort(key=lambda value: (value["start_counter"], value["visit_index"]))
        references = [value for value in values if value["reference_positive"]]
        if not references:
            continue
        first = references[0]
        positives = [
            value for value in values
            if value["candidate_positive"]
            and value["start_counter"] >= first["start_counter"]
        ]
        discovered = positives[0] if positives else None
        output.append({
            "key_id": key_id,
            "rate_hz": first["rate_hz"],
            "first_reference_case_id": first["case_id"],
            "first_reference_visit_index": first["visit_index"],
            "first_strategy_case_id": discovered["case_id"] if discovered else None,
            "first_strategy_visit_index": discovered["visit_index"] if discovered else None,
            "lag_seconds": (
                (discovered["start_counter"] - first["start_counter"]) / first["rate_hz"]
                if discovered else None
            ),
            "never_discovered": discovered is None,
            "strategy_was_positive_before_first_reference": any(
                value["candidate_positive"]
                and value["start_counter"] < first["start_counter"]
                for value in values
            ),
        })
    return output


def summarize(rows):
    baseline = {
        metric: sum(median(item[metric] for item in row["baseline_times"]) for row in rows)
        for metric in ("cpu_ms", "wall_ms")
    }
    components = {
        kind: {
            metric: sum(row["cost_components"][kind][metric] for row in rows)
            for metric in ("cpu_ms", "wall_ms")
        }
        for kind in ("blind", "check", "state")
    }
    strategy = {
        metric: sum(components[kind][metric] for kind in components)
        for metric in ("cpu_ms", "wall_ms")
    }
    coverage = Counter(
        row["reference_positive_outcome"]
        for row in rows if row["reference_positive"]
    )
    latency = latency_rows(rows)
    result = {
        "receiver_visits": len(rows),
        "actions": dict(Counter(row["action"] for row in rows)),
        "blind_searches": sum(row["result_kind"] == "blind" for row in rows),
        "fast_checks": sum(row["attempted_fast_check"] for row in rows),
        "unknown_visits": sum(row["result_kind"] == "unknown" for row in rows),
        "reference_positive_visits": sum(row["reference_positive"] for row in rows),
        "reference_positive_coverage": dict(coverage),
        "candidate_positive_visits": sum(row["candidate_positive"] for row in rows),
        "costs": {
            "offline_full_coverage_baseline": baseline,
            "strategy_components": components,
            "strategy_total": strategy,
        },
        "cpu_speedup": baseline["cpu_ms"] / strategy["cpu_ms"],
        "wall_speedup": baseline["wall_ms"] / strategy["wall_ms"],
        "blind_cost_only_cpu_upper_bound_speedup": (
            baseline["cpu_ms"] / components["blind"]["cpu_ms"]
            if components["blind"]["cpu_ms"] else None
        ),
        "blind_cost_only_wall_upper_bound_speedup": (
            baseline["wall_ms"] / components["blind"]["wall_ms"]
            if components["blind"]["wall_ms"] else None
        ),
        "reaches_10x_compute_ratio": baseline["cpu_ms"] / strategy["cpu_ms"] >= 10,
        "preserves_reference_positive_coverage": (
            coverage.get("lost", 0) == 0 and coverage.get("unknown", 0) == 0
        ),
        "discovery_latency": {
            "keys_with_reference_positive": len(latency),
            "never_discovered_keys": sum(item["never_discovered"] for item in latency),
            "lags_seconds": [item["lag_seconds"] for item in latency
                             if item["lag_seconds"] is not None],
            "per_key": latency,
        },
    }
    finite_lags = result["discovery_latency"]["lags_seconds"]
    result["discovery_latency"]["maximum_lag_seconds"] = (
        max(finite_lags) if finite_lags else None
    )
    result["discovery_latency"]["median_lag_seconds"] = (
        median(finite_lags) if finite_lags else None
    )
    return result


def run_policy(cases, reference_rows, dataset_path, config, cadence, library):
    tracker = Tracker(Policy(**config["policy"]))
    schedule = CadenceSchedule(cadence)
    repetitions = config["repetitions"]
    rows = []
    with ExitStack() as stack:
        geometries = sorted({(case["rate_hz"], case["edge"]) for case in cases})
        blind = {
            geometry: stack.enter_context(NativeDwell(library, *geometry, 512))
            for geometry in geometries
        }
        fast = {
            geometry: stack.enter_context(NativeKnownStateV3(*geometry, library=library))
            for geometry in geometries
        }
        for case in cases:
            raw_path = (dataset_path.parent / case["raw_npy"]["path"]).resolve()
            if not raw_path.is_relative_to(dataset_path.parent):
                raise ValueError("IQ path outside dev dataset")
            if sha256(raw_path) != case["raw_npy"]["sha256"].removeprefix("sha256:"):
                raise ValueError("IQ hash mismatch")
            raw = np.load(raw_path, allow_pickle=False)
            original_hash = hashlib.sha256(raw).hexdigest()
            rate = case["rate_hz"]
            geometry = rate, case["edge"]
            for receiver in range(2):
                reference_row = reference_rows[(case["case_id"], receiver)]
                reference_payload = reference_row["reference"]
                reference = None
                if reference_payload is not None:
                    from tracking import Observation
                    reference = Observation(**reference_payload)
                key = Key(
                    case["session_id"], receiver, case["channel"], case["edge"], rate
                )
                key_id = ":".join(map(str, (
                    key.session, key.receiver, key.channel, key.edge, key.rate_hz
                )))
                start = case["source_start_counter"]
                state_cpu_start = time.process_time_ns()
                state_wall_start = time.perf_counter_ns()
                blind_due, blind_reason = schedule.begin(key, start)
                prediction, tracker_reason = tracker.begin(key, start, case["visit_index"])
                state_cpu_ms = (time.process_time_ns() - state_cpu_start) / 1e6
                state_wall_ms = (time.perf_counter_ns() - state_wall_start) / 1e6
                observation = None
                attempted = None
                detail = None
                action_times = []
                attempted_fast = False
                result_kind = "unknown"
                if blind_due:
                    def acquire(raw=raw, receiver=receiver, geometry=geometry):
                        samples = np.ascontiguousarray(raw[:, receiver, :])
                        native = blind[geometry].run(samples, maximum=1, seeded=False)
                        return blind_observation(native), native

                    observation, detail, action_times = timed(acquire, repetitions)
                    attempted = observation
                    action = blind_reason
                    result_kind = "blind"
                elif prediction is not None:
                    attempted_fast = True
                    left = prediction.window * (rate // 50)

                    def measure(raw=raw, left=left, receiver=receiver, rate=rate,
                                prediction=prediction, geometry=geometry):
                        native = fast[geometry].measure(
                            raw[left:left + rate // 50, receiver, :],
                            prediction.epoch_samples,
                            prediction.scoring_cfo_hz,
                            expected_physical_cfo_hz=prediction.cfo_hz,
                            recover_timing=False,
                            frame_limit=config["frame_limit"],
                        )
                        native["scoring_cfo_hz"] = prediction.scoring_cfo_hz
                        return fast_observation(native, prediction.window), native

                    attempted, detail, action_times = timed(measure, repetitions)
                    if tracker.accepts(key, prediction, attempted):
                        observation = attempted
                        action = "cache_hit"
                        result_kind = "fast"
                    else:
                        action = "failed_fast_unknown"
                else:
                    action = f"{tracker_reason}_unknown"
                update_cpu_start = time.process_time_ns()
                update_wall_start = time.perf_counter_ns()
                if observation is not None:
                    tracker.update(
                        key, start, case["visit_index"], observation,
                        discovery=result_kind == "blind",
                    )
                state_cpu_ms += (time.process_time_ns() - update_cpu_start) / 1e6
                state_wall_ms += (time.perf_counter_ns() - update_wall_start) / 1e6
                action_cpu = median(item["cpu_ms"] for item in action_times) if action_times else 0
                action_wall = median(item["wall_ms"] for item in action_times) if action_times else 0
                matched = bool(
                    reference and observation
                    and reference_match(reference, observation, rate)
                )
                reference_positive = bool(reference and reference.positive)
                rows.append({
                    "case_id": case["case_id"],
                    "session_id": case["session_id"],
                    "visit_index": case["visit_index"],
                    "rate_hz": rate,
                    "edge": case["edge"],
                    "channel": case["channel"],
                    "receiver": receiver,
                    "key_id": key_id,
                    "start_counter": start,
                    "action": action,
                    "result_kind": result_kind,
                    "blind_due": blind_due,
                    "tracker_reason": tracker_reason,
                    "attempted_fast_check": attempted_fast,
                    "prediction": asdict(prediction) if prediction else None,
                    "reference": asdict(reference) if reference else None,
                    "attempted_observation": asdict(attempted) if attempted else None,
                    "observation": asdict(observation) if observation else None,
                    "reference_positive": reference_positive,
                    "candidate_positive": bool(observation and observation.positive),
                    "matched_reference": matched,
                    "reference_positive_outcome": classify_reference(
                        reference_positive, matched, result_kind
                    ),
                    "baseline_times": reference_row["baseline_times"],
                    "action_times": action_times,
                    "cost_components": {
                        "blind": {
                            "cpu_ms": action_cpu if result_kind == "blind" else 0,
                            "wall_ms": action_wall if result_kind == "blind" else 0,
                        },
                        "check": {
                            "cpu_ms": action_cpu if attempted_fast else 0,
                            "wall_ms": action_wall if attempted_fast else 0,
                        },
                        "state": {"cpu_ms": state_cpu_ms, "wall_ms": state_wall_ms},
                    },
                    "native_detail": unpack(detail) if isinstance(detail, ct.Structure) else detail,
                })
            if hashlib.sha256(raw).hexdigest() != original_hash:
                raise ValueError("caller IQ mutated")
    return rows


def run(args):
    signal.alarm(240)
    if args.output.exists():
        raise FileExistsError(args.output)
    dataset_path = args.dataset.resolve()
    reference_path = args.reference.resolve()
    config_path = args.config.resolve()
    dataset = json.loads(dataset_path.read_text())
    reference = json.loads(reference_path.read_text())
    config = json.loads(config_path.read_text())
    if reference["split"] != "dev" or reference["dataset_sha256"] != sha256(dataset_path):
        raise ValueError("reference must be the matching dev replay")
    cases = sorted(
        (case for case in dataset["cases"] if case["split"] == "dev"),
        key=lambda case: (case["session_id"], case["visit_index"]),
    )
    if any(case["split"] != "dev" for case in cases) or not cases:
        raise ValueError("cadence replay is dev-only")
    reference_rows = {
        (row["case_id"], row["rx"]): row for row in reference["rows"]
    }
    if len(reference_rows) != 2 * len(cases):
        raise ValueError("incomplete offline reference")
    library = build_library_v3()
    receipt_path = library.with_suffix(".so.build.json")
    native_receipt = json.loads(receipt_path.read_text())
    for source, expected in native_receipt["sources_sha256"].items():
        if sha256(source) != expected:
            raise ValueError("native source receipt mismatch")
    sources = [Path(__file__), ROOT / "tracking.py"]
    source_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in sources}
    immutable_hashes = {
        "dataset": sha256(dataset_path),
        "reference": sha256(reference_path),
        "config": sha256(config_path),
        "native": sha256(library),
        "native_receipt": sha256(receipt_path),
    }
    policies = []
    for cadence in config["cadence_seconds"]:
        rows = run_policy(
            cases, reference_rows, dataset_path, config, float(cadence), library
        )
        policies.append({
            "cadence_seconds": float(cadence),
            "rows": rows,
            "summary": summarize(rows),
        })
    if immutable_hashes != {
        "dataset": sha256(dataset_path),
        "reference": sha256(reference_path),
        "config": sha256(config_path),
        "native": sha256(library),
        "native_receipt": sha256(receipt_path),
    }:
        raise ValueError("experiment input changed during replay")
    if source_hashes != {
        str(path.relative_to(ROOT)): sha256(path) for path in sources
    }:
        raise ValueError("cadence source changed during replay")
    for source, expected in native_receipt["sources_sha256"].items():
        if sha256(source) != expected:
            raise ValueError("native source changed during replay")
    payload = {
        "schema": "org.leo.research.adaptive-cadence-dev/v1",
        "scope": "dev-only causal server replay; reduced search coverage experiment",
        "fresh_holdout_opened": False,
        "dataset_sha256": sha256(dataset_path),
        "offline_reference_sha256": sha256(reference_path),
        "offline_reference_role": "evaluation and baseline cost only; never state or proposals",
        "config_sha256": sha256(config_path),
        "config": config,
        "source_sha256": source_hashes,
        "native_binary_sha256": sha256(library),
        "native_build_receipt_sha256": sha256(receipt_path),
        "host": platform.uname()._asdict(),
        "policies": policies,
        "limitations": [
            "unknown visits are neither absence evidence nor cached detections",
            "speedup from skipped searches is reported separately from coverage and latency",
            "the 5 s cadence exceeds the unchanged tracker 2 s expiry after failed checks",
            "real observations are unlabeled; reference positives are detector references",
            "server timing is not ARM qualification",
        ],
    }
    with args.output.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps([
        {"cadence_seconds": policy["cadence_seconds"], **policy["summary"]}
        for policy in policies
    ], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset/cases.json")
    parser.add_argument("--reference", type=Path, default=ROOT / "dev_dual_cfo_v4.json")
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    run(parser.parse_args())
