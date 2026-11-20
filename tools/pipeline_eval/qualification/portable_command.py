"""Seal and score the full portable saved-recording command on DS29-0082."""

import argparse
import gzip
import json
from pathlib import Path
from unittest.mock import patch

from .. import iq_service, original_receiver, portable_receiver, whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES, arm_outcome, distance_km
from . import accelerated_command_results as controls
from . import capture_release, field_exact_waveform_results, portable_field_parity
from . import portable_field_scores as checks
from .armijo_finish_results import pack
from .capture_whole_results import ARCHIVED
from .full_held_scores import held_references
from .full_v5_check import BULK, _load_case, _sha
from .prefix_figures import csv_file

CASE = "DS29-0082"
PORTABLE = "portable_command"
POSITION = "positions.jsonl.gz"
REPORT_ROOT = ROOT / "reports/2026_11_19_receiver_screening"
OUT = REPORT_ROOT / "native-receiver/portable-command"
HISTORICAL = REPORT_ROOT / "pilot-search-and-region/field-exact-waveform"
PROTOCOL_SHA = "a02ab2e937aa2ab87c94e9ead2f9fc2425f0ba6a52881644a971b0500ee4a4ba"
HISTORICAL_PREDICTION_SHA = "1120835b1f43533690fb99c69ac5da4c576c0d06c20121b16335fc0fcc867a25"
HISTORICAL_SCORE_SHA = "8d233332669b34274b937c3a1f973fe072bccdba5f26966c07a3bdc36733234b"
read = whole_iq.read


def historical(case, request):
    predictions = read(
        whole_iq.checked(HISTORICAL / "prediction-lock.json", HISTORICAL_PREDICTION_SHA)
    )
    files = predictions["files"]
    checks.checked_files(HISTORICAL, files, (POSITION, "native.json.gz", "audit.json"))
    archive_source = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
    native = read(archive_source)
    with gzip.open(HISTORICAL / "native.json.gz", "rt") as stream:
        exact = field_exact_waveform_results.parity(json.load(stream), native)
    if exact["classification"] != "exact":
        raise ValueError("historical full-IQ replay must be exact against signed native factors")

    directory = HISTORICAL / "receipts/archive"
    position = read(directory / "position.json")
    archive_request = read(directory / "recording/request.json")
    receipt = read(directory / "terminal.json")
    plan = read(directory / "plan.json")
    attempt = read(directory / "raw.json")
    whole_iq.verify_request(
        archive_request,
        request,
        native_path=str(archive_source),
        native_sha256="sha256:" + case["native"]["sha256"],
    )
    if (
        not iq_service.succeeded(receipt)
        or receipt["log_sha256"] != _sha(directory / "service.log")
        or attempt["request_sha256"] != _sha(directory / "recording/request.json")
        or attempt["native_sha256"] != "sha256:" + case["native"]["sha256"]
        or plan["source_lock_sha256"] != files["source-lock.json"]
    ):
        raise ValueError("archived compact result lacks a matched independent service receipt")
    with gzip.open(HISTORICAL / POSITION, "rt") as stream:
        (prediction,) = [r for r in map(json.loads, stream) if r["method"] == ARCHIVED]
    if (
        prediction["id"] != CASE
        or prediction["native_sha256"] != case["native"]["sha256"]
        or prediction["original_request_sha256"] != case["request"]["sha256"]
        or prediction["catalog_sha256"] != case["catalog"]["sha256"]
        or prediction["tile"] != case["regions"][0]
        or prediction["result"] != position
    ):
        raise ValueError("archived factor prediction differs from sealed execution")
    return native, prediction, exact, read(HISTORICAL / "audit.json"), plan


def clock(path, internal):
    values = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().rpartition(": ")
        if sep:
            values[key] = value
    elapsed = values["Elapsed (wall clock) time (h:mm:ss or m:ss)"]
    seconds = sum(
        float(value) * 60**power for power, value in enumerate(reversed(elapsed.split(":")))
    )
    if seconds + 0.01 < internal or values["Exit status"] not in {"0", "1"}:
        raise ValueError("whole-command clock or terminal exit differs from the runner result")
    return dict(
        elapsed_s=seconds,
        user_s=float(values["User time (seconds)"]),
        system_s=float(values["System time (seconds)"]),
        supervisor_rss_kib=int(values["Maximum resident set size (kbytes)"]),
        exit_code=int(values["Exit status"]),
    )


def v5_directory(case):
    return (BULK / case["request"]["path"]).parent.parent


def v5_sources(case):
    directory = v5_directory(case)
    return {
        str(path): _sha(path)
        for role in ROLES
        for path in (
            directory / role / "experimental-request.json",
            directory / f"{role}-execution.json",
        )
    }


def seal(work, output):
    protocol = whole_iq.checked(output / "PROTOCOL.md", PROTOCOL_SHA)
    if (output / "prediction-lock.json").exists():
        raise FileExistsError("the prediction comparison is already sealed")
    preflight = (work.parent / "protocol.sha256").read_text().split()
    if not preflight or preflight[0] != PROTOCOL_SHA:
        raise ValueError("prelaunch protocol digest does not match the published protocol")
    case = _load_case(CASE)
    request, causal = checks.causal_authority(case)
    archive, previous, exact, historical_audit, archive_plan = historical(case, request)
    files = read(work / "run-seal.json")["files"]
    checks.checked_files(work, files, checks.RUN_KEYS)
    lock, summary = (read(work / name) for name in checks.RUN_KEYS)
    capture = capture_release.read_capture(case)
    producer = capture_release.producer(case, capture)
    capture["case"] = {name: case[name] for name in ("id", "session_id", "run_id")}
    expected_chunks = original_receiver.chunks(case)
    actual_chunks = [tuple(chunk) for _, _, spans in lock["workers"] for chunk in spans]
    if (
        lock["case"] != case
        or summary["id"] != CASE
        or lock["smoke"]
        or summary["mode"] != "full"
        or sorted(actual_chunks) != sorted(expected_chunks)
        or lock["capture"] != capture
        or lock["producer"] != str(producer.root)
        or lock["cpus"] != [3, 4, 5, 6, 7]
        or [worker[0] for worker in lock["workers"]] != lock["cpus"]
        or (lock["raw_limit_s"], lock["position_limit_s"]) != (600, 180)
        or lock["receiver"] != archive_plan["receiver"]
        or lock["receiver_files"] != original_receiver.receiver_assets(Path(lock["receiver"]))
        or lock["sources"].get(portable_receiver.__file__) != _sha(Path(portable_receiver.__file__))
    ):
        raise ValueError("live portable command differs from the frozen full DS29 protocol")
    original_receiver.configure(work)
    raw, visits, samples = checks.raw_state(work, lock, summary, files)
    native_sha = summary.get("native_sha256")
    native = None
    if native_sha is not None:
        if not raw["complete"] or files.get("native.json") != native_sha.removeprefix("sha256:"):
            raise ValueError("native position input lacks a complete signed raw replay")
        native = read(work / "native.json")
        if native["provenance"]["detector_sha256"] != original_receiver.recording.digest(
            lock["detector"]
        ):
            raise ValueError("native position input lacks the portable numeric source identity")
    result, fit = checks.position_record(
        work, lock, summary, files, request, native_sha, raw["complete"]
    )
    proof, differences, ambiguous = portable_field_parity.compare(native, visits, archive)
    attempts, attempt_summary = checks.collect_attempts(visits)
    clocks = archive["delivery_clocks"]
    clock_path = work.parent / "whole-command.time"
    measurement = clock(clock_path, summary["command_wall_s"])
    if measurement["exit_code"] != int(summary["status"] in ("failed", "unavailable", "timed_out")):
        raise ValueError("external command receipt disagrees with the sealed result")
    raw["largest_worker_rss_kib"] = max(
        (
            worker["terminal"]["end"]["rss_peak_kib"]
            for worker in raw["workers"].values()
            if worker["terminal"]
        ),
        default=None,
    )
    previous["archived_native_sha256"] = previous["paired_capture_sha256"]
    fresh = previous | dict(method=PORTABLE, native_sha256=native_sha, result=result)
    comparison = controls.compare_positions([fresh, previous | {"method": controls.ARCHIVE}])[
        PORTABLE
    ]
    save_json(
        output / "command-evidence.json",
        dict(
            raw=raw,
            fit=fit,
            whole_command=measurement,
            command_intervals=summary["command_wall_s"],
            status=result["status"],
            cpu_roster=lock["cpus"],
            detector=lock["detector"],
            recorded_delivery_span_s=(clocks[-1]["monotonic_ns"] - clocks[0]["monotonic_ns"]) / 1e9,
            authenticated_iq_bytes=sum(visit["input_bytes"] for visit in visits),
            historical_raw={
                key: value
                for key, value in historical_audit["raw"].items()
                if key not in ("workers", "parity")
            },
            historical_fits=historical_audit["position"],
            archive_fit_comparison=comparison,
            causal=causal,
            attempts=attempt_summary,
        ),
    )
    save_json(output / "native-parity.json", proof | {"historical_exact_vs_signed": exact})
    files_to_seal = {
        POSITION: pack(output, POSITION, [fresh, previous]),
        "native-differences.jsonl.gz": pack(output, "native-differences.jsonl.gz", differences),
        "equivalent-peaks.jsonl.gz": pack(output, "equivalent-peaks.jsonl.gz", ambiguous),
        "portable-attempts.jsonl.gz": pack(output, "portable-attempts.jsonl.gz", attempts),
    }
    if samples:
        csv_file(output / "raw-visits.csv", samples)
        files_to_seal["raw-visits.csv"] = _sha(output / "raw-visits.csv")
    for path, name in (
        (work / "run-seal.json", "live-run-seal.json"),
        (work / "source-lock.json", "source-lock.json"),
        (work / "summary.json", "command-summary.json"),
        (clock_path, "whole-command.time"),
    ):
        write(output / name, path.read_bytes())
        files_to_seal[name] = _sha(output / name)
    if native is not None:
        path = output / "native.json.gz"
        write(path, gzip.compress((work / "native.json").read_bytes(), compresslevel=5, mtime=0))
        files_to_seal[path.name] = _sha(path)
    for name in ("command-evidence.json", "native-parity.json", protocol.name):
        files_to_seal[name] = _sha(output / name)
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=[CASE],
            files=files_to_seal,
            work=str(work),
            historical_prediction_sha256=HISTORICAL_PREDICTION_SHA,
            original_v5_sources=v5_sources(case),
            scoring_sources={
                module.__file__: _sha(Path(module.__file__))
                for module in (checks, portable_field_parity, controls)
            }
            | {str(Path(__file__)): _sha(Path(__file__))},
        ),
    )


def position_scores(predictions, truth):
    rows = []
    for prediction in predictions:
        result = prediction["result"]
        for arm in ARMS:
            endpoint = result["arms"][arm]
            status, reason = arm_outcome(result, endpoint)
            rows.append(
                dict(
                    id=prediction["id"],
                    method=prediction["method"],
                    arm=arm,
                    status=status,
                    reason=reason,
                    error_km=distance_km(endpoint["latlon"], truth),
                    forced_error_km=distance_km(endpoint.get("forced_latlon"), truth),
                    rf_rms_hz=endpoint.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(arm + "_frequency_score"),
                )
            )
    return rows


def score(output):
    from . import portable_command_report as report

    prediction_lock = read(output / "prediction-lock.json")
    checks.checked_files(output, prediction_lock["files"], (POSITION, "command-evidence.json"))
    if (
        prediction_lock["cases"] != [CASE]
        or prediction_lock["files"].get("PROTOCOL.md") != PROTOCOL_SHA
    ):
        raise ValueError("prediction lock does not bind the predeclared DS29 comparison")
    for key in ("scoring_sources", "original_v5_sources"):
        for path, digest in prediction_lock[key].items():
            whole_iq.checked(Path(path), digest)
    historical_score = read(whole_iq.checked(HISTORICAL / "score-lock.json", HISTORICAL_SCORE_SHA))
    if historical_score["prediction_lock_sha256"] != HISTORICAL_PREDICTION_SHA:
        raise ValueError("historical score used a different prediction lock")
    checks.checked_files(HISTORICAL, historical_score["files"], ("v5-roles.csv",))
    with gzip.open(output / POSITION, "rt") as stream:
        predictions = list(map(json.loads, stream))
    if [row["method"] for row in predictions] != [PORTABLE, ARCHIVED]:
        raise ValueError(
            "prediction seal must contain fresh and independently fitted archived results"
        )
    _, (reference,) = held_references(None, [CASE])
    case = _load_case(CASE)
    with patch.object(controls, "V5_ARCHIVE", v5_directory(case).parent):
        v5, receipts = controls.original_v5_scores(case, reference)
    save_json(output / "original-v5-receipts.json", receipts)
    rows = position_scores(predictions, reference["truth"]) + v5
    quality = checks.accuracy(
        [
            row
            | {
                "method": {PORTABLE: checks.PORTABLE, ARCHIVED: checks.ARCHIVE}.get(
                    row["method"], row["method"]
                )
            }
            for row in rows
        ]
    )
    for prediction in predictions:
        endpoints = prediction["result"]["arms"]
        key = checks.PORTABLE if prediction["method"] == PORTABLE else checks.ARCHIVE
        quality["fitted_c_minus_c0"][key]["endpoint_separation_km"] = distance_km(
            *(endpoints[arm]["latlon"] for arm in ARMS)
        )
    csv_file(output / "scores.csv", rows)
    save_json(output / "scores.json", quality)
    report_files = report.publish(output, rows, quality)
    score_files = (
        "prediction-lock.json",
        "scores.csv",
        "scores.json",
        "original-v5-receipts.json",
        *report_files,
    )
    save_json(
        output / "score-lock.json",
        dict(
            cases=[CASE],
            historical_score_sha256=HISTORICAL_SCORE_SHA,
            files=prediction_lock["files"] | {name: _sha(output / name) for name in score_files},
        ),
    )
    report.render(output)
    save_json(
        output / "report-seal.json",
        dict(
            files={
                path.relative_to(output).as_posix(): _sha(path)
                for path in sorted(output.rglob("*"))
                if path.is_file() and path.name != "report-seal.json"
            }
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "score"))
    parser.add_argument("--work", type=local_output)
    parser.add_argument("--out", type=local_output, default=OUT)
    args = parser.parse_args()
    if args.action == "seal":
        if args.work is None:
            parser.error("seal needs --work from the measured public command")
        seal(args.work, args.out)
    else:
        score(args.out)


if __name__ == "__main__":
    main()
