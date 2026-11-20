"""Fit paired no-repair v5 positions with a bounded spectral IQ splice."""

import argparse
import gzip
import json
import os
import sys
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.__main__ import ROOT, THREAD_ENV, encoded, local_output, references, write
from tools.pipeline_eval.qualification import spectral_grid_eval
from tools.pipeline_eval.qualification.full_v5_check import (
    BULK,
    PRODUCERS,
    _bind_producer,
    _from_production,
    _load_case,
    _measure,
    _probe,
    _sha,
)
from tools.pipeline_eval.qualification.pilot_kernel_eval import _digest, _windows
from tools.pipeline_eval.qualification.recording_to_v5 import bind_request, digest, save
from tools.pipeline_eval.scoring import distance_km, distribution, validate_result
from tools.pipeline_eval.variants import (
    anchor_grid,
    anchor_receiver,
    pilot_kernel,
    spectral_grid,
    v5_lean,
)

STAGE_ONLY = ROOT / "reports/2026_11_19_receiver_frontend/spectral"
BOUNDARY = "Partial spectral IQ replay plus capture-era archive to full no-repair v5"


def verify_window(window, output, scheduled):
    payload = output.model_dump(mode="json")
    if (
        window.sequence != scheduled["sequence"]
        or window.acquisition["global_visit"] != scheduled["visit"]
        or window.iq_sha256 != scheduled["iq_sha256"]
        or output.status != scheduled["status"]
        or _digest(encoded(payload)) != scheduled["payload_sha256"]["spectral"]
    ):
        raise ValueError("Fresh spectral output differs from the authenticated stage-only visit")


def replay(case, directory):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case_id = case["id"]
    policy = FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    sources = (Path(spectral_grid_eval.__file__), spectral_grid.SOURCE,
               Path(spectral_grid.__file__), pilot_kernel.SOURCE)
    source_sha = {p.name: _sha(p) for p in sources}
    spectral_so, tiled_so = directory / "spectral.so", directory / "tiled.so"
    spectral_grid.compile_filter(spectral_so)
    pilot_kernel.compile_filter(tiled_so)
    library_sha = {p.name: _sha(p) for p in (spectral_so, tiled_so)}
    grid = spectral_grid.SpectralGrid(spectral_so, anchor_grid.native_grid(tiled_so))
    sampler = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)
    rows, stage_receipts = [], {}
    with (patch.object(acquisition, "_folded_anchor_score_grid", grid.score_grid),
          patch.object(acquisition, "_retain_score_map_peaks", grid.retain_peaks),
          patch.object(fast_scan_scores, "fractional_take", sampler)):
        for split, segment in spectral_grid_eval.SCHEDULE.items():
            receipt_path = STAGE_ONLY / f"{case_id}-{split}.json.gz"
            stage = json.loads(gzip.decompress(receipt_path.read_bytes()))
            if (stage["case"], stage["split"], stage["segment"], stage["producer"],
                    stage["source_sha256"]) != (case_id, split, segment, producer, source_sha):
                raise ValueError("Stage-only receipt does not name the current producer and method")
            stage_receipts[split] = _sha(receipt_path)
            windows = _windows(case, segment, spectral_grid_eval.SEQUENCES)
            for window, prior in zip(windows, stage["rows"], strict=True):
                grid.receipts.clear()
                wall, cpu = perf_counter(), process_time()
                output = analyze_window(window, window.receiver_ids, None, policy)
                wall, cpu = perf_counter() - wall, process_time() - cpu
                verify_window(window, output, prior)
                probes = [_probe(window, r.receiver_id, map(_from_production, r.candidates))
                          for r in output.receivers]
                if output.status == "processed" and (
                    tuple(p["receiver_id"] for p in probes) != (0, 1)
                    or not grid.receipts
                    or any(r["fallback"] is not None for r in grid.receipts)
                ):
                    raise ValueError("Processed visit did not yield both fresh spectral receivers")
                rows.append(dict(
                    split=split, sequence=window.sequence, visit=output.visit,
                    iq_sha256=window.iq_sha256, sample_start=output.sample_start,
                    sample_end=output.sample_end, policy_status=output.status, reason=output.reason,
                    payload_sha256=prior["payload_sha256"]["spectral"], production=probes,
                    native=probes, equal_status=True, detector_cpu_s=cpu, detector_wall_s=wall,
                    coarse_grids=grid.receipts.copy(), output=output.model_dump(mode="json"),
                ))
                print(case_id, "spectral replay", split, output.visit, output.status, flush=True)
    if library_sha != {p.name: _sha(p) for p in (spectral_so, tiled_so)}:
        raise ValueError("Spectral library changed during replay")
    if len({r["visit"] for r in rows}) != len(rows):
        raise ValueError("Partial spectral replay must list each scheduled visit once")
    return dict(
        case=case_id, producer=producer, rows=rows, source_sha256=digest(source_sha),
        kernel_sha256=library_sha[spectral_so.name], archive_stage_receipt_sha256=stage_receipts,
        libraries=library_sha,
    )


def compose(case, archive, measurement):
    audit = _measure(case, measurement["rows"], archive["source"]["sample_rate_hz"])
    if not audit["archive_exclusions_equal"] or audit["different_probe_keys"]:
        raise ValueError("Fresh spectral probes or exclusions differ from the capture-era archive")
    native, changed = anchor_receiver.splice_probes(archive, dict(measurement, archive_audit=audit))
    native["provenance"]["scope"] = BOUNDARY
    if changed or native["source"]["probes"] != archive["source"]["probes"]:
        raise ValueError("Spliced detector input changed the archived fractional candidates")
    return native, audit


def _worker(request_path, result_path):
    render = v5_lean._position_result

    def capture(inference, **options):
        result = render(inference, **options)
        native = inference["native"]
        result["metrics"].update(
            observations_sha256=digest(native["observations"]),
            tracks_sha256=digest(native["tracks"]),
            final_owners_sha256={arm: digest(inference["owners"][arm]) for arm in v5_lean.ARMS},
        )
        return result

    with patch.object(v5_lean, "_position_result", capture):
        v5_lean._worker(request_path, result_path)


def _child_cpu_s():
    resource = getrusage(RUSAGE_CHILDREN)
    return resource.ru_utime + resource.ru_stime


def fit(case, native_path, folder, method):
    folder.mkdir(exist_ok=False)
    bound = bind_request(case, native_path, folder / "bound-request.json")
    wall, cpu = perf_counter(), _child_cpu_s()
    result = v5_lean.run_bound_worker(
        bound, folder / "position", Path(__file__), worker_args=("--worker",),
    )
    wall_s, cpu_s = perf_counter() - wall, _child_cpu_s() - cpu
    if result["status"] != "ok":
        raise RuntimeError(f"{case['id']} {method} v5 failed: {result.get('reason')}")
    request = json.loads((folder / "position/request.json").read_bytes())
    if request["job"]["native_input"]["sha256"] != bound["native_sha256"]:
        raise ValueError("Actual v5 request did not consume the verified native document")
    result["metrics"].update(position_attempted=True, position_cpu_s=cpu_s, position_wall_s=wall_s)
    for arm in v5_lean.ARMS:
        result["arms"][arm]["rf_rms_hz"] = result["metrics"][f"{arm}_conditional_rms_hz"]
    print(case["id"], method, "fresh v5", wall_s, flush=True)
    return dict(
        id=case["id"], method=method, input_sha256=bound["native_sha256"],
        request_sha256=_sha(folder / "position/request.json"),
        worker_wall_s=wall_s, worker_cpu_s=cpu_s, result=result,
    )


def verify_pair(control, trial):
    if control["input_sha256"] == trial["input_sha256"]:
        raise ValueError("Spectral composite was not given a distinct input identity")
    before, after = (record["result"] for record in (control, trial))
    keys = ("observations_sha256", "tracks_sha256", "final_owners_sha256")
    if any(key not in before["metrics"] or before["metrics"][key] != after["metrics"].get(key)
           for key in keys):
        raise ValueError("Fresh v5 preparation or final orbit-arc ownership changed")
    if before["arms"] != after["arms"]:
        raise ValueError("The same observation and orbit arcs yielded different v5 arm outputs")
    numerical_keys = tuple(
        f"{arm}_{metric}" for arm in v5_lean.ARMS for metric in (
            "associated_observations", "frequency_score", "conditional_rms_hz",
        )
    )
    if any(before["metrics"].get(key) != after["metrics"].get(key) for key in numerical_keys):
        raise ValueError("Paired v5 numerical fit metrics differ")


def position(case_id, directory):
    case = _load_case(case_id)
    archive_path = BULK / case["native"]["path"]
    if _sha(archive_path) != case["native"]["sha256"]:
        raise ValueError("Capture-era archive changed")
    measurement = replay(case, directory)
    archive = json.loads(archive_path.read_bytes())
    native, audit = compose(case, archive, measurement)
    composite = directory / "partial-iq-native.json"
    save(composite, native)
    # Retain the fresh detector measurements and exact exclusions for independent validation.
    receipt = directory / "spectral-replay.json.gz"
    write(receipt, gzip.compress(encoded(dict(measurement, archive_audit=audit)), mtime=0))
    work = ((archive_path, "spectral_grid_capture_control"), (composite, "spectral_grid"))
    if case_id == "DS29-0082":
        work = work[::-1]
    fits = {method: fit(case, path, directory / method, method) for path, method in work}
    control, trial = fits["spectral_grid_capture_control"], fits["spectral_grid"]
    verify_pair(control, trial)
    panel = "ds26-common127" if case["panel"] == "DS26" else "roof16"
    _, (reference,) = references(panel, [case_id])
    for arm in v5_lean.ARMS:
        measured = control["result"]["arms"][arm]["latlon"]
        frozen = reference["reference"]["baseline"][arm]["latlon"]
        if distance_km(measured, frozen) > 1e-6:
            raise ValueError("Fresh capture-era control disagrees with the frozen v5 position")
    rows = measurement["rows"]
    processed = archive["provenance"]["processed_windows"]
    valid = sum(r["policy_status"] == "processed" for r in rows)
    trial["result"]["boundary"] = BOUNDARY
    trial["result"]["metrics"].update(
        scheduled_visits=len(rows), fresh_iq_visits=valid,
        replayed_capture_exclusions=len(rows) - valid, archived_valid_visits=processed - valid,
        recording_visits=archive["provenance"]["window_count"],
        fresh_receiver_probe_rows=audit["exact_probe_rows"],
        archived_receiver_probe_rows=len(archive["source"]["probes"]) - audit["exact_probe_rows"],
        detector_cpu_s=sum(r["detector_cpu_s"] for r in rows),
        detector_wall_s=sum(r["detector_wall_s"] for r in rows),
        identical_capture_era_factors=True, identical_prepared_arcs=True,
        control_input_sha256=control["input_sha256"],
    )
    trial.update(
        variant="partial-iq-spectral", detector_receipt_sha256=_sha(receipt),
        implementation_sha256=digest([measurement["source_sha256"], _sha(Path(__file__))]),
    )
    for row in (control, trial):
        validate_result(row["result"])
        row["position_error_km"] = {arm: distance_km(
            row["result"]["arms"][arm]["latlon"], reference["truth"]
        ) for arm in v5_lean.ARMS}
        save(directory / (row["method"] + ".json"), row)


def package(directory):
    control_method, trial_method = "spectral_grid_capture_control", "spectral_grid"
    methods = {control_method: "control-positions", trial_method: "positions"}
    records = {method: [] for method in methods}
    for case_id in PRODUCERS:
        source_hash = _load_case(case_id)["native"]["sha256"]
        pair = {}
        for method in methods:
            row = json.loads((directory / case_id / f"{method}.json").read_bytes())
            if row["id"] != case_id or row["method"] != method:
                raise ValueError("Position receipt belongs to a different experiment")
            validate_result(row["result"])
            row["source_archive_sha256"] = source_hash
            pair[method] = row
            records[method].append(row)
        control, trial = pair[control_method], pair[trial_method]
        if (
            control["input_sha256"] != f"sha256:{source_hash}"
            or trial["result"]["metrics"]["control_input_sha256"] != control["input_sha256"]
        ):
            raise ValueError("Position pair does not bind the frozen capture-era archive")
        verify_pair(control, trial)
    for method, basename in methods.items():
        raw = b"".join(encoded(row) + b"\n" for row in records[method])
        write(directory / f"{basename}.jsonl.gz", gzip.compress(raw, mtime=0))
    summaries = {method: {
        arm: distribution(row["position_error_km"][arm] for row in rows)
        for arm in v5_lean.ARMS
    } for method, rows in records.items()}
    write(directory / "error-distributions.json", encoded(summaries) + b"\n")


def main():
    if sys.argv[-1:] == ["--worker"] and len(sys.argv) == 4:
        _worker(*sys.argv[1:3])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--case", choices=PRODUCERS)
    mode.add_argument("--package", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = local_output(args.out)
    if out.is_relative_to(BULK / "leo"):
        parser.error("choose an output outside the capture archive")
    if args.package:
        package(out)
        return
    cpus = os.sched_getaffinity(0)
    if cpus not in ({12}, {13}) or any(os.environ.get(k) != "1" for k in THREAD_ENV):
        parser.error("pin CPU 12 or 13 and set numerical runtime thread counts to one")
    out.mkdir(parents=True, exist_ok=False)
    position(args.case, out)


if __name__ == "__main__":
    main()
