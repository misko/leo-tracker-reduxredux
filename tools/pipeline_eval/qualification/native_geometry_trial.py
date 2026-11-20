"""Replay four authenticated survey windows through the wideband native interval wrapper."""

import argparse
import ctypes as ct
import gzip
import json
import os
import subprocess
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

from ..__main__ import encoded, save_json, write
from ..scoring import validate_result
from ..variants.iq_stream import load_windows
from .full_v5_check import (
    BUDGET_S,
    BULK,
    MARGIN_GATE,
    NATIVE_LIBRARY,
    PRODUCERS,
    REPO,
    _bind_producer,
    _from_native,
    _from_production,
    _load_case,
    _measure,
    _probe,
    _sha,
    compare_probes,
)

WIDEBAND = (
    REPO
    / "reports/2026_09_30_native_adaptive_deployment/ds9/receiver-authority-ablation-v1"
    / "wideband-research/artifacts/host/libleo-adaptive-detector.so"
)
SEQUENCES = (0, 2)
RATE = 10_000_000
TIMES = RATE // 50
INTERVAL_MODE = 5
DISCRETE = (
    "candidate_rank",
    "epoch_sample",
    "passed_margin_gate",
    "fractional_epoch_status",
    "passed_fractional_margin_gate",
)
CFO = (
    "acquired_cfo_hz",
    "residual_cfo_hz",
    "tracking_cfo_hz",
    "fractional_residual_cfo_hz",
    "fractional_tracking_cfo_hz",
)
SCORES = (
    "exact_score",
    "control_score",
    "margin",
    "fractional_epoch_offset_samples",
    "fractional_exact_score",
    "fractional_control_score",
    "fractional_margin",
)


def ranked_candidate(rank, candidate):
    acquired = candidate["acquired_cfo_hz"]
    tracked = candidate["tracking_cfo_hz"]
    scores = {key: candidate[key] for key in ("exact_score", "control_score", "margin")}
    fractional = candidate["fractional_epoch"]
    return dict(
        candidate_rank=rank,
        epoch_sample=candidate["epoch"],
        acquired_cfo_hz=acquired,
        residual_cfo_hz=tracked - acquired,
        tracking_cfo_hz=tracked,
        **scores,
        passed_margin_gate=scores["margin"] >= MARGIN_GATE,
        fractional_epoch_status=fractional["status"],
        fractional_epoch_offset_samples=fractional["offset_samples"],
        **{
            f"fractional_{key}": fractional[key]
            for key in (
                "exact_score",
                "control_score",
                "margin",
                "residual_cfo_hz",
                "tracking_cfo_hz",
            )
        },
    )


def compare_ranked(reference, candidate):
    """Compare common scientific fields at their published ranks."""
    maximum = defaultdict(float)
    mismatches = defaultdict(list)
    for rank, (baseline, tested) in enumerate(zip(reference, candidate, strict=False)):
        for field in (*DISCRETE, *CFO, *SCORES):
            left, right = (row.get(field) for row in (baseline, tested))
            if field == "passed_fractional_margin_gate":
                left, right = (
                    row["fractional_margin"] is not None and row["fractional_margin"] >= MARGIN_GATE
                    for row in (baseline, tested)
                )
            if field in DISCRETE or left is None or right is None:
                equal = left == right
            else:
                delta = abs(left - right)
                maximum[field] = max(maximum[field], delta)
                equal = delta <= (1e-6 if field in CFO else 1e-10)
            if not equal:
                mismatches[field].append([rank, left, right])
    return dict(
        reference_count=len(reference),
        tested_count=len(candidate),
        equal_within_tolerance=len(reference) == len(candidate) and not mismatches,
        max_absolute_deltas=dict(maximum),
        mismatches=dict(mismatches),
    )


def _inspect_abi(path, exact, control, geometries):
    """Probe the unmodified libraries using the true rate, templates and bounds."""
    library = ct.CDLL(str(path))
    library.leo_native_glrt_layout.argtypes = [ct.c_uint32] * 3 + [ct.POINTER(ct.c_size_t)] * 2
    library.leo_native_glrt_create_with_mode.argtypes = [
        ct.POINTER(ct.c_void_p),
        ct.c_uint32,
        ct.c_void_p,
        ct.c_void_p,
        ct.c_size_t,
        ct.c_uint32,
    ]
    library.leo_native_glrt_destroy.argtypes = [ct.c_void_p]
    library.leo_native_glrt_set_server_reference_geometry.argtypes = [
        ct.c_void_p,
        ct.POINTER(ct.c_double),
        ct.c_double,
        ct.c_double,
    ]
    times, rows = ct.c_size_t(), ct.c_size_t()
    layout = library.leo_native_glrt_layout(RATE, 20, 20, ct.byref(times), ct.byref(rows))
    context = ct.c_void_p()
    status = library.leo_native_glrt_create_with_mode(
        ct.byref(context),
        RATE,
        exact.ctypes.data,
        control.ctypes.data,
        len(exact),
        INTERVAL_MODE,
    )
    if status:
        raise RuntimeError(f"native ABI control failed context creation with status {status}")
    try:
        setters = [
            library.leo_native_glrt_set_server_reference_geometry(
                context,
                (ct.c_double * 2)(*entry["receiver_centers_hz"]),
                *entry["residual_bounds_hz"],
            )
            for entry in geometries
        ]
    finally:
        library.leo_native_glrt_destroy(context)
    return dict(
        sha256=_sha(path),
        layout_status=layout,
        layout_complex_times=times.value,
        layout_rows=rows.value,
        short_window_export=hasattr(library, "leo_native_glrt_analyze_short_window"),
        geometry_statuses=setters,
    )


def _capture_reference(window, policy):
    from leo.analysis.starlink.acquisition import _bounded_grid
    from leo.scanner import fast_scan_analysis as analysis
    from leo.scanner import fast_scan_detector as detector

    invocations, acquired = [], []
    analyze = analysis.analyze_glrt64_dwell
    acquire = detector.acquire_symbolwise

    def observe(values, configuration, *, edge, search_geometry):
        invocations.append(search_geometry)
        return analyze(values, configuration, edge=edge, search_geometry=search_geometry)

    def observe_anchors(probe, rate, calibration, *, config, edge):
        acquired.append(
            dict(
                receiver_id=calibration.receiver_id,
                anchors=len(config.anchor_symbols),
            )
        )
        return acquire(probe, rate, calibration, config=config, edge=edge)

    with (
        patch.object(analysis, "analyze_glrt64_dwell", observe),
        patch.object(
            detector,
            "acquire_symbolwise",
            observe_anchors,
        ),
    ):
        start, cpu = perf_counter(), process_time()
        result = analysis.analyze_window(window, window.receiver_ids, None, policy)
        wall_s, cpu_s = perf_counter() - start, process_time() - cpu
    if result.status != "processed" or len(invocations) != 1:
        raise ValueError("the predeclared window failed the pinned capture policy")
    geometry = invocations[0]
    lo, hi = geometry.residual_cfo_min_hz, geometry.residual_cfo_max_hz
    return result, dict(
        receiver_centers_hz=[c.center_hz for c in geometry.receiver_calibrations],
        residual_bounds_hz=[lo, hi],
        residual_grid_hz=_bounded_grid(lo, hi, 80_000),
        acquisition_calls=acquired,
        wall_s=wall_s,
        cpu_s=cpu_s,
    )


def _manifest(directory, windows, geometries, exact, control):
    exact_path, control_path = directory / "exact.c128", directory / "control.c128"
    exact.tofile(exact_path)
    control.tofile(control_path)
    rows = []
    for index, (window, geometry) in enumerate(zip(windows, geometries, strict=True)):
        input_path = directory / f"{index}.ci16"
        window.samples.tofile(input_path)
        if "sha256:" + _sha(input_path) != window.iq_sha256:
            raise ValueError("exported detector input changed the authenticated CI16 bytes")
        fields = (
            index,
            RATE,
            20,
            20,
            exact_path,
            control_path,
            input_path,
            *geometry["receiver_centers_hz"],
            *geometry["residual_bounds_hz"],
            window.iq_sha256,
        )
        rows.append("\t".join(map(str, fields)))
    manifest = directory / "visits.tsv"
    manifest.write_text("\n".join(rows) + "\n")
    return manifest


def _replay_native(binary, manifest, windows, *, scalar=False):
    mode = (
        "--deployed-server-wrapper-fractional"
        if scalar
        else "--deployed-server-interval-fractional"
    )
    result = subprocess.run(
        [
            str(binary),
            "--manifest",
            str(manifest),
            mode,
            "--thermal-path",
            "/nonexistent",
            "--thermal-scale",
            "1",
            "--thermal-offset",
            "0",
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if result.returncode:
        raise RuntimeError(f"wideband short-window replay failed: {result.stderr.strip()}")
    records = [json.loads(line) for line in result.stdout.splitlines()]
    calls = [record["result"] for record in records if "result" in record]
    for index, (call, window) in enumerate(zip(calls, windows, strict=True)):
        if (
            call["sequence"] != index
            or call["rate_hz"] != RATE
            or call["dwell_ms"] != 20
            or call["stride_ms"] != 20
            or call["profile"]["prepared_complex_times"] != TIMES
            or call["metadata"] != window.iq_sha256
            or tuple(
                (r["receiver_id"], r["probe_index"], r["probe_start_ms"]) for r in call["rows"]
            )
            != tuple((receiver, 0, 0) for receiver in window.receiver_ids)
        ):
            raise ValueError("native replay did not acknowledge the exact recorded input support")
    return calls


def trial(case_id, maintained, wideband_replay, ordinary, *, scalar_control=False):
    import numpy as np

    from leo.analysis.starlink import templates
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.contracts.fast_scan_native import FastScanPolicyV2

    case, policy = _load_case(case_id), FastScanPolicyV2()
    identity = _bind_producer(case, PRODUCERS[case_id], policy)
    locator = case["recording"]["segments"][0]
    windows = load_windows(
        dict(
            recording_path=str(BULK / locator["path"]),
            recording_sha256="sha256:" + locator["sha256"],
        ),
        SEQUENCES,
    )
    edge = windows[0].target["edge"]
    for window in windows:
        if (
            window.sample_rate_hz != RATE
            or window.samples.shape != (TIMES, 2, 2)
            or window.samples.dtype != np.dtype("<i2")
            or window.target["edge"] != edge
        ):
            raise ValueError("recorded windows differ from the predeclared detector geometry")
    exact, control = (
        np.asarray(templates.qin_edge_pilot_frame(RATE, edge, **kwargs), dtype="<c16")
        for kwargs in ({}, {"symbol_roll": templates.CONTROL_SYMBOL_ROLL})
    )
    production, geometries = zip(*(_capture_reference(w, policy) for w in windows), strict=True)
    controls = {
        name: _inspect_abi(path, exact, control, geometries)
        for name, path in (
            ("maintained", maintained),
            ("unmodified_wideband", WIDEBAND),
        )
    }
    with TemporaryDirectory(prefix="leo-native-geometry-trial-") as scratch:
        manifest = _manifest(Path(scratch), windows, geometries, exact, control)
        calls = _replay_native(wideband_replay, manifest, windows)
        if scalar_control:
            scalar_calls = _replay_native(wideband_replay, manifest, windows, scalar=True)
        else:
            scalar_calls = []

    rows = []
    with NativeShortWindow(
        str(ordinary), exact, control, sample_rate_hz=RATE, fractional_epoch=True
    ) as prior:
        for window, reference, geometry, wideband in zip(
            windows,
            production,
            geometries,
            calls,
            strict=True,
        ):
            start, cpu = perf_counter(), process_time()
            previous = prior.analyze(window.samples, include_timings=True)["rows"]
            timing = dict(wall_s=perf_counter() - start, cpu_s=process_time() - cpu)
            row = dict(
                visit=window.acquisition["global_visit"],
                iq_sha256=window.iq_sha256,
                policy_status=reference.status,
                input_bytes=window.samples.nbytes,
                sample_start=reference.sample_start,
                sample_end=reference.sample_end,
                channel=window.target["channel"],
                edge=edge,
                geometry=geometry,
                target_rf_hz=window.target["rf_center_hz"],
                actual_if_hz=window.acquisition["actual_if_center_hz"],
                lnb_lo_hz=window.target["lnb_lo_hz"],
                wideband_timing=dict(
                    cpu_s=wideband["call_cpu_ms"] / 1000, wall_s=wideband["call_wall_ms"] / 1000
                ),
                ordinary_timing=timing,
                production=[],
                native=[],
                comparisons=[],
            )
            for expected, tested, ordinary_row in zip(
                reference.receivers, wideband["rows"], previous, strict=True
            ):
                rx = expected.receiver_id
                if tested["receiver_id"] != rx or ordinary_row["receiver_id"] != rx:
                    raise ValueError("receiver order differs across detectors")
                original = _probe(window, rx, map(_from_production, expected.candidates))
                row["production"].append(original)
                expected_ranked = [c.model_dump() for c in expected.candidates]
                comparison = dict(receiver=rx)
                for key, detector_row in (("wideband", tested), ("ordinary", ordinary_row)):
                    candidates = detector_row["candidates"]
                    probe = _probe(
                        window, rx, (_from_native(rank, c) for rank, c in enumerate(candidates))
                    )
                    if key == "wideband":
                        row["native"].append(probe)
                    tested_ranked = [ranked_candidate(r, c) for r, c in enumerate(candidates)]
                    comparison[key] = dict(
                        ranked=compare_ranked(expected_ranked, tested_ranked),
                        physical=compare_probes(original, probe, RATE),
                        row_cpu_ms=detector_row["timings_ms"]["total_cpu"],
                        peer_retry=bool(detector_row["proposal_tracking_fallback"]),
                    )
                row["comparisons"].append(comparison)
            rows.append(row)

    audit = _measure(case, rows, RATE)
    processed = audit["archived_status_counts"]["processed_windows"]
    scalar_comparison = [
        dict(
            visit=row["visit"],
            cpu_s=scalar["call_cpu_ms"] / 1000,
            wall_s=scalar["call_wall_ms"] / 1000,
            candidate_payloads_equal_by_receiver=[
                reference["candidates"] == tested["candidates"]
                for reference, tested in zip(interval["rows"], scalar["rows"], strict=True)
            ],
        )
        for row, interval, scalar in zip(rows, calls, scalar_calls, strict=scalar_control)
    ]
    for row in rows:
        del row["production"], row["native"]
    return dict(
        case=case_id,
        producer=identity,
        cpus=sorted(os.sched_getaffinity(0)),
        segment_sha256=locator["sha256"],
        sample_rate_hz=RATE,
        template_sha256=dict(
            exact=sha256(exact.tobytes()).hexdigest(), control=sha256(control.tobytes()).hexdigest()
        ),
        wideband_replay_sha256=_sha(wideband_replay),
        ordinary_library_sha256=_sha(ordinary),
        controls=controls,
        archive_audit=audit,
        two_core_cpu_budget_seconds_per_valid_window=2 * BUDGET_S / processed,
        windows=rows,
        scalar_comparison=scalar_comparison,
    )


def write_predictions(directory):
    """Publish the measured detector boundary for the figure workflow."""
    records = []
    for case_id in PRODUCERS:
        report = json.loads((directory / f"{case_id}.json").read_bytes())
        windows = report["windows"]
        comparisons = [r for w in windows for r in w["comparisons"]]
        cpu_s = sum(w["wideband_timing"]["cpu_s"] for w in windows)
        wall_s = sum(w["wideband_timing"]["wall_s"] for w in windows)
        result = dict(
            status="ok",
            boundary="Wideband native acquisition and fractional GLRT on authenticated IQ windows",
            reason=(
                "Two recorded windows checked per case. Full recording positioning was unmeasured. "
                "Measured detector CPU exceeded the two-core, 15-minute budget."
            ),
            metrics=dict(
                windows=len(windows),
                receiver_probes=len(comparisons),
                ranked_candidates=sum(r["wideband"]["ranked"]["tested_count"] for r in comparisons),
                within_tolerance_probes=sum(
                    r["wideband"]["ranked"]["equal_within_tolerance"] for r in comparisons
                ),
                exact_historical_projections=report["archive_audit"]["exact_probe_rows"],
                detector_cpu_s=cpu_s,
                detector_wall_s=wall_s,
                control_s=sum(w["geometry"]["wall_s"] for w in windows),
                candidate_s=wall_s,
                two_core_cpu_budget_seconds_per_valid_window=(
                    report["two_core_cpu_budget_seconds_per_valid_window"]
                ),
            ),
        )
        validate_result(result)
        input_sha256 = sha256(encoded([w["iq_sha256"] for w in windows])).hexdigest()
        records.append(
            dict(
                id=case_id,
                method="native_geometry",
                input_sha256=input_sha256,
                implementation_sha256=report["wideband_replay_sha256"],
                worker_wall_s=wall_s,
                worker_cpu_s=cpu_s,
                result=result,
            )
        )
    data = b"".join(encoded(record) + b"\n" for record in records)
    write(directory / "positions.jsonl.gz", gzip.compress(data, mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(PRODUCERS), required=True)
    parser.add_argument("--maintained", type=Path, required=True)
    parser.add_argument("--wideband-replay", type=Path, required=True)
    parser.add_argument("--ordinary", type=Path, default=NATIVE_LIBRARY)
    parser.add_argument("--scalar-control", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1 or any(
        os.environ.get(key) != "1"
        for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        parser.error("use one CPU of affinity and one numerical thread")
    if args.out.resolve().is_relative_to(BULK / "leo"):
        parser.error("write the trial outside the archive")
    save_json(
        args.out,
        trial(
            args.case,
            args.maintained.resolve(),
            args.wideband_replay.resolve(),
            args.ordinary.resolve(),
            scalar_control=args.scalar_control,
        ),
    )


if __name__ == "__main__":
    main()
