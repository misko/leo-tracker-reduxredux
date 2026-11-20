"""Fit paired v5 positions on authenticated partial-IQ composites."""

import argparse
import gzip
import json
import os
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output, write
from ..scoring import validate_result
from ..variants import anchor_receiver, orbit_projector
from .full_v5_check import BULK, PRODUCERS, _load_case, _sha
from .pilot_kernel_eval import alternating_order
from .recording_to_v5 import bind_request, digest, save

BOUNDARY = "8 scheduled IQ windows per recording plus archived detections to the v5 cavity fit"


def compose(original, measurement, mode):
    rows = measurement["rows"]
    audit = measurement["archive_audit"]
    if (
        not any(row["policy_status"] == "processed" for row in rows)
        or audit["different_probe_keys"]
        or not all(
            row["equal_payload"]
            and row["equal_coarse_peak_keys"]
            and row["production"] == row["native"]
            for row in rows
        )
    ):
        raise ValueError("partial-IQ observations differ or have no valid waveform window")
    selected = [dict(row, native=row["production"]) for row in rows] if mode == "control" else rows
    replay = dict(
        measurement,
        rows=selected,
        source_sha256=digest(measurement["source_sha256"]),
        kernel_sha256=measurement["library_sha256"][mode],
    )
    native, changed = anchor_receiver.splice_probes(original, replay)
    native["provenance"]["scope"] = BOUNDARY
    return native, changed


def position_pair(case_id, receipt, directory):
    case = _load_case(case_id)
    measurement = json.loads(gzip.decompress(receipt.read_bytes()))
    archive = BULK / case["native"]["path"]
    frozen_sha256 = case["native"]["sha256"]
    if (
        measurement["case"] != case_id
        or measurement["archive_audit"]["archive_sha256"] != frozen_sha256
        or _sha(archive) != frozen_sha256
    ):
        raise ValueError(
            "detector evidence and source do not bind the same archived observation set"
        )
    original = json.loads(archive.read_bytes())
    order = alternating_order(list(PRODUCERS).index(case_id), 0)
    results = []
    for method in order:
        folder = directory / method
        folder.mkdir(parents=True, exist_ok=False)
        native, changed = compose(original, measurement, method)
        native_path = folder / "partial-iq-native.json"
        save(native_path, native)
        bound = bind_request(case, native_path, folder / "partial-iq-request.json")
        position = folder / "position"
        position.mkdir()
        started = perf_counter()
        result = orbit_projector.run(bound, position)
        wall_s = perf_counter() - started
        result["boundary"] = BOUNDARY
        result["metrics"].update(
            scheduled_windows=len(measurement["rows"]),
            valid_windows=sum(row["policy_status"] == "processed" for row in measurement["rows"]),
            fresh_fractional_gate_passes=sum(
                row["fractional_gate_passes"] for row in measurement["rows"]
            ),
            changed_probe_rows=changed,
            native_to_v5_wall_s=wall_s,
        )
        validate_result(result)
        row = dict(
            id=case_id,
            method=method,
            recipe="compact projector through the v5 cavity decision",
            input_sha256=bound["native_sha256"],
            implementation_sha256=measurement["library_sha256"][method],
            detector_receipt_sha256=_sha(receipt),
            worker_wall_s=wall_s,
            result=result,
        )
        print(case_id, method, result["status"], wall_s, flush=True)
        save(folder / "receipt.json", row)
        results.append(row)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(PRODUCERS), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1:
        parser.error("pin the pair to one CPU")
    directory = local_output(args.work)
    if directory.is_relative_to(BULK / "leo"):
        parser.error("choose an output outside the recording archive")
    rows = position_pair(args.case, args.receipt, directory)
    write(args.out, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


if __name__ == "__main__":
    main()
