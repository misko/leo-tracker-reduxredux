"""Collect the original pre-continuation factors from one saved publication pair."""

import argparse
import gzip
import json
import sys
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from leo.contracts.digests import canonical_digest
from tools import algo08_scan
from tools.pipeline_eval.qualification import blind_compact_run
from tools.pipeline_eval.variants.experimental.receiver_acquisition_profile import NativeFactors
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer

DETECTOR_SHA256 = "950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13"


class FactorLedger:
    def __init__(self):
        self.rows = []
        self.native_cpu_ns = []
        self.pending = None

    @contextmanager
    def span(self, stage):
        if stage != "native_factors" or self.pending is not None:
            raise ValueError("each ledger row must follow exactly one native factor call")
        start = process_time_ns()
        yield
        self.pending = process_time_ns() - start

    def record(self, probe):
        visit, lane = probe["visit_index"], probe["receiver_id"]
        if self.pending is None or lane != len(self.rows) % 2:
            raise ValueError("native lane call and continuation row are not paired")
        if self.rows:
            previous = self.rows[-1]["visit_index"]
            if (lane == 1 and visit != previous) or (lane == 0 and visit <= previous):
                raise ValueError("pre-continuation rows are out of chronological order")
        if len(probe["candidates"]) > 2:
            raise ValueError("pre-continuation row exceeds the frozen two-factor contract")
        self.rows.append(deepcopy(probe))
        self.native_cpu_ns.append(self.pending)
        self.pending = None


def verify(acquired, expected, ledger):
    actual_source, expected_source = acquired["source"], expected["source"]
    for field in (
        "session_id", "input_manifest_sha256", "raw_recording_authority_digest",
        "analysis_manifest_sha256", "probes",
    ):
        if actual_source[field] != expected_source[field]:
            raise ValueError(f"acquired {field} differs from the matched saved detections")
    for field in ("detector_sha256", "window_count", "processed_windows", "excluded_windows"):
        if acquired["provenance"][field] != expected["provenance"][field]:
            raise ValueError(f"acquired {field} differs from the matched saved provenance")
    selected = actual_source["probes"]
    if ledger.pending is not None or len(ledger.rows) != len(selected):
        raise ValueError("ledger has missing or extra pre-continuation rows")
    for before, after in zip(ledger.rows, selected, strict=True):
        if any(before[key] != value for key, value in after.items() if key != "candidates"):
            raise ValueError("continuation output differs in visit metadata")
        if any(candidate not in before["candidates"] for candidate in after["candidates"]):
            raise ValueError("continuation output is absent from its recorded factor set")


def collect(pair_path, assets):
    pair = json.loads(pair_path.read_bytes())
    specification = pair["candidate_specification"]
    frozen_binary = Path(specification["detector"])
    if (specification["detector_sha256"] != DETECTOR_SHA256
            or sha256(frozen_binary.read_bytes()).hexdigest() != DETECTOR_SHA256):
        raise ValueError("factor ledger requires the frozen packed receiver")
    session = pair["runs"]["candidate"]["receipt"]["session_id"]
    root = pair_path.parent / "candidate"
    inventory = json.loads((root / "fast-scan-inputs" / f"{session}.json").read_bytes())
    inventory_sha = canonical_digest(inventory)
    detector_id = "algo08-v2-" + canonical_digest([algo08_scan.ALGO08V2, inventory_sha])[7:39]
    expected_path = root / "fast-scan-automatic-work" / detector_id / "detections.json"
    expected_bytes = expected_path.read_bytes()
    expected = json.loads(expected_bytes)

    capture = FactorLedger()
    stock_continuation = blind_compact_run.Continuation
    stock_native = blind_compact_run.Native
    stock_detector = algo08_scan.detector

    class RecordedContinuation(stock_continuation):
        def select(self, probe):
            capture.record(probe)
            return super().select(probe)

    def timed_native(path, pilot):
        receiver = stock_native(path, pilot)
        native_factors = receiver.lib.cancellation_factors
        receiver.lib.cancellation_factors = NativeFactors(native_factors, capture)
        return receiver

    def bound_detector(method, edge, *, binary=None, pilot=None):
        return stock_detector(method, edge, binary=frozen_binary, pilot=pilot)

    wall_start, cpu_start = perf_counter_ns(), process_time_ns()
    with (
        compressed_input_buffer(),
        patch.object(algo08_scan, "detector", bound_detector),
        patch.dict(algo08_scan.PINS, {"cancellation-factors.so": DETECTOR_SHA256}),
        patch.object(blind_compact_run, "Native", timed_native),
        patch.object(blind_compact_run, "Continuation", RecordedContinuation),
    ):
        acquired = algo08_scan.acquire(session, inventory_sha, inventory, assets)
    cpu_ns, wall_ns = process_time_ns() - cpu_start, perf_counter_ns() - wall_start
    verify(acquired, expected, capture)
    source = acquired["source"]
    return dict(
        schema_version=1,
        recording=inventory["recording_name"],
        session_id=session,
        detector_sha256=DETECTOR_SHA256,
        input_manifest_sha256=inventory_sha,
        raw_authority=source["raw_recording_authority_digest"],
        ordered_selected_sha256=canonical_digest(source["probes"]),
        saved_detections_sha256=sha256(expected_bytes).hexdigest(),
        acquisition_cpu_ns=cpu_ns,
        acquisition_wall_ns=wall_ns,
        window_count=acquired["provenance"]["window_count"],
        excluded_windows=acquired["provenance"]["excluded_windows"],
        factor_counts=Counter(len(row["candidates"]) for row in capture.rows),
        rows=capture.rows,
        native_cpu_ns=capture.native_cpu_ns,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    ledger = collect(args.pair, args.assets)
    content = json.dumps(ledger, separators=(",", ":"), allow_nan=False).encode()
    sys.stdout.buffer.write(gzip.compress(content, mtime=0))
