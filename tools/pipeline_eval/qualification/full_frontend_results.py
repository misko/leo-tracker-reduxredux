"""Pack complete ordinary raw replays and rescore the six fixed timing recordings."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path

from ..__main__ import encoded, read_predictions, references, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from .full_v5_check import _load_case, _sha
from .prefix_figures import TIMING_IDS, csv_file


def collect(directories, out):
    predictions, receipts = {}, {}
    for directory in directories:
        path = directory / "predictions.jsonl"
        records = read_predictions(path)
        if len(records) != 1:
            raise ValueError(f"expected one complete recording in {path}")
        case_id, row = next(iter(records.items()))
        if case_id not in TIMING_IDS or case_id in predictions:
            raise ValueError(f"unexpected or duplicated timing recording {case_id}")
        case = _load_case(case_id)
        result = row["result"]
        if (
            result["boundary"]
            != "Complete recorded IQ to native GLRT and frozen no-repair v5 position"
        ):
            raise ValueError(f"expected the ordinary complete detector in {path}")
        native_path = directory / "native.json"
        document = json.loads(native_path.read_bytes())
        native_sha = _sha(native_path)
        request_path = directory / "experimental-request.json"
        request = json.loads(request_path.read_bytes())
        job = request["job"]
        if (
            request["role"] != "baseline"
            or job["evaluation_reference"] is not None
            or job["native_input"]["sha256"] != "sha256:" + native_sha
            or job["identity"]
            != dict(
                input_sha256="sha256:" + native_sha,
                session_id=case["session_id"],
                run_id="experiment-" + native_sha[:32],
            )
        ):
            raise ValueError(
                f"v5 inference was not bound to the fresh detector input for {case_id}"
            )
        metrics = result["metrics"]
        if (
            case["session_id"] != document["source"]["session_id"]
            or document["provenance"].get("detector_mode", "ordinary") != "ordinary"
            or metrics["recording_windows"] != case["recording"]["window_count"]
            or metrics["processed_windows"] + metrics["invalid_capture"]
            != metrics["recording_windows"]
            or metrics["probe_rows"] != 2 * metrics["processed_windows"]
        ):
            raise ValueError(f"raw replay does not cover the expected capture for {case_id}")
        clocks = document["delivery_clocks"]
        span = (clocks[-1]["monotonic_ns"] - clocks[0]["monotonic_ns"]) / 1e9
        if (
            len(clocks) != metrics["recording_windows"]
            or span <= 0
            or metrics.get("window_delivery_span_s", span) != span
        ):
            raise ValueError(f"delivery clock span disagrees with the recording for {case_id}")
        # The first two full replays stored the delivery clocks ahead of the span metric.
        metrics["window_delivery_span_s"] = span
        receipts[case_id] = dict(
            prediction_sha256=_sha(path),
            native_sha256=native_sha,
            replay_request_sha256=_sha(request_path),
            input_manifest_sha256=document["source"]["input_manifest_sha256"],
            analysis_manifest_sha256=document["source"]["analysis_manifest_sha256"],
            detector_sha256=document["provenance"]["detector_sha256"],
            frozen_request_sha256=case["request"]["sha256"],
        )
        predictions[case_id] = row
    if set(predictions) != set(TIMING_IDS):
        raise ValueError("the six-recording raw qualification is incomplete")
    raw = b"".join(encoded(predictions[key]) + b"\n" for key in TIMING_IDS)
    write(out / "positions.jsonl.gz", gzip.compress(raw, mtime=0))
    write(
        out / "recording-receipts.json",
        encoded(dict(rows_sha256=sha256(raw).hexdigest(), recordings=receipts)) + b"\n",
    )


def score(out):
    rows = read_predictions(out / "positions.jsonl.gz")
    if set(rows) != set(TIMING_IDS):
        raise ValueError("score the complete fixed timing panel")
    refs = {r["id"]: r for panel in ("ds26-all159", "roof16") for r in references(panel, None)[1]}
    positions, times, summaries = [], [], []
    for case_id in TIMING_IDS:
        row, ref = rows[case_id], refs[case_id]
        result = row["result"]
        validate_result(result)
        metrics = result["metrics"]
        for arm in ARMS:
            control = ref["reference"]["baseline"][arm]
            positions.append(
                dict(
                    id=case_id,
                    dataset=ref["group"],
                    arm=arm,
                    status=result["status"],
                    v5_km=control["error_km"],
                    native_km=distance_km(result["arms"][arm]["latlon"], ref["truth"]),
                    v5_matched_rms_hz=control["matched_rf_rms_hz"],
                    native_conditional_rms_hz=metrics.get(f"{arm}_conditional_rms_hz"),
                    v5_observations=control["matched_observations"],
                    native_observations=metrics.get(f"{arm}_associated_observations"),
                )
            )
        times.append(
            dict(
                id=case_id,
                visits=metrics["recording_windows"],
                valid=metrics["processed_windows"],
                excluded=metrics["invalid_capture"],
                recorded_s=metrics["window_delivery_span_s"],
                detector_cpu_s=metrics["detector_cpu_s"],
                raw_and_assembly_wall_s=metrics["raw_and_assembly_wall_s"],
                position_wall_s=metrics.get("candidate_s"),
                end_to_end_wall_s=row["worker_wall_s"],
                elapsed_over_recorded=row["worker_wall_s"] / metrics["window_delivery_span_s"],
            )
        )
    for dataset in ("DS26", "DS29"):
        for arm in ARMS:
            group = [r for r in positions if r["dataset"] == dataset and r["arm"] == arm]
            for method in ("v5", "native"):
                errors = [r[f"{method}_km"] for r in group if r[f"{method}_km"] is not None]
                stats = distribution(errors)
                summaries.append(
                    dict(
                        dataset=dataset,
                        arm=arm,
                        method=method,
                        attempts=len(group),
                        fixes=len(errors),
                        within_5_km=sum(e <= 5 for e in errors),
                        median_km=stats["p50"],
                        p95_km=stats["p95"],
                        worst_km=stats["max"],
                    )
                )
    csv_file(out / "position-errors.csv", positions)
    csv_file(out / "runtime.csv", times)
    csv_file(out / "distributions.csv", summaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--recording", type=Path, action="append")
    args = parser.parse_args()
    if args.recording:
        collect(args.recording, args.out)
    score(args.out)


if __name__ == "__main__":
    main()
