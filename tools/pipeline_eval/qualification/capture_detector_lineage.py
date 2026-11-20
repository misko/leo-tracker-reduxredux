"""Trace capture-era detector provenance before matching the frozen factor rows."""

import argparse
import gzip
import json
import platform
import sys
from dataclasses import asdict, replace
from pathlib import Path
from statistics import median
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants.iq_stream import load_windows
from . import capture_detector_replay, capture_release
from .full_v5_check import (
    BULK,
    NATIVE_LIBRARY,
    _bind_producer,
    _from_native,
    _load_case,
    _probe,
    _sha,
)

REPORT = ROOT / "reports/2026_11_19_receiver_screening/detector-origins/lineage"
SCHEDULE = ((0, (1, 6)), (6, (1, 6)), (13, (1, 6)))
CASES = ("DS26-0036", "DS26-0237", "DS29-0082", "DS29-0174")
MODES = ("capture", "ordinary")
ORDINARY = ROOT / "reports/2026_11_19_receiver_frontend/ordinary/recording-receipts.json"
SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
LIB_BUILD = NATIVE_LIBRARY.with_name("build-receipt.json")


def windows(case):
    for segment, seq in SCHEDULE:
        source = case["recording"]["segments"][segment]
        path = (BULK / source["path"]).resolve()
        if not path.is_relative_to(BULK / "leo/fast-scan-recordings"):
            raise ValueError("frozen capture is not on the permitted local corpus")
        for window in load_windows(
            dict(recording_path=str(path), recording_sha256="sha256:" + source["sha256"]), seq
        ):
            yield segment, window


def source_lineage(case):
    from leo.analysis.starlink import _native_acquisition, acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner import fast_scan_analysis, fast_scan_detector

    capture = capture_release.read_capture(case)
    release = capture_release.producer(case, capture)
    policy = FastScanPolicyV2()
    producer = _bind_producer(case, release, policy)
    modules = (
        acquisition,
        _native_acquisition,
        fast_scan_scores,
        fast_scan_analysis,
        fast_scan_detector,
    )
    roots = [release.root, release.root.parent, release.root.parent.parent]
    names = (
        "deployment-manifest.json",
        "native-source-parity.json",
        "runtime-manifest.json",
        "release-revision.txt",
    )
    manifests = [root / name for root in roots for name in names if (root / name).is_file()]
    primitive = Path(acquisition.__file__).parent
    sources = [Path(m.__file__) for m in modules]
    sources.extend(
        primitive / name for name in ("_native_acquisition.c", "_native_acquisition_grid.inc")
    )
    sources.extend(manifests)
    if not all(path.is_relative_to(release.root) for path in sources[: len(modules)]):
        raise ValueError("capture scientific modules do not come from the attested release")
    return (
        capture,
        policy,
        dict(
            capture=producer,
            sources={str(p): _sha(p) for p in sources},
            architecture=platform.machine(),
            python=sys.executable,
            python_version=platform.python_version(),
            numpy=np.__version__,
            capture_coarse_backend=acquisition._folded_anchor_score_grid_backend(),
            ordinary_library_sha256=_sha(NATIVE_LIBRARY),
            ordinary_build_receipt_sha256=_sha(LIB_BUILD),
        ),
    )


def intersection(config, center):
    return replace(
        config,
        residual_cfo_min_hz=max(config.residual_cfo_min_hz, -400_000 - center),
        residual_cfo_max_hz=min(config.residual_cfo_max_hz, 400_000 - center),
    )


def trace_capture(window, policy, *, shrink=False):
    from leo.scanner import fast_scan_detector

    calls = []
    original = fast_scan_detector.acquire_symbolwise

    def trace(samples, rate, calibration, *, edge, config):
        center = calibration.center_hz
        if shrink:
            config = intersection(config, center)
        result = original(samples, rate, calibration, edge=edge, config=config)
        calls.append(
            dict(
                receiver=calibration.receiver_id,
                center_hz=center,
                config=asdict(config),
                candidates=[
                    dict(
                        rank=c.rank,
                        coarse_epoch=c.coarse_epoch_sample,
                        coarse_absolute_hz=c.coarse_residual_cfo_hz + center,
                        refined_epoch=c.refined_epoch_sample,
                        acquired_cfo_hz=c.absolute_cfo_hz,
                    )
                    for c in result.candidates
                ],
            )
        )
        return result

    with patch.object(fast_scan_detector, "acquire_symbolwise", trace):
        result, probes = capture_detector_replay.scan_capture_window(
            window, window.receiver_ids, policy
        )
    return result.status, probes, calls


def replay(case_id):
    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.scanner.fast_scan_analysis import analyze_window

    case = _load_case(case_id)
    capture, policy, provenance = source_lineage(case)
    begin = perf_counter_ns()
    selected = list(windows(case))
    decode = (perf_counter_ns() - begin) / 1e6
    exact = np.asarray(qin_edge_pilot_frame(10_000_000, capture["edge"]), dtype="<c16")
    rolled = np.asarray(
        qin_edge_pilot_frame(10_000_000, capture["edge"], symbol_roll=CONTROL_SYMBOL_ROLL),
        dtype="<c16",
    )
    rows, intervention = [], None
    with NativeShortWindow(
        str(NATIVE_LIBRARY), exact, rolled, sample_rate_hz=10_000_000, fractional_epoch=True
    ) as native:
        for index, (segment, window) in enumerate(selected):
            values = {}

            def detect(w, receivers, values=values):
                values.update(native.analyze(w.samples, include_timings=True))
                return tuple(FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in receivers)

            def call(mode, window=window, values=values, detect=detect):
                if mode == "capture":
                    return capture_detector_replay.scan_capture_window(
                        window, window.receiver_ids, policy
                    )
                result = analyze_window(window, window.receiver_ids, None, policy, detector=detect)
                probes = [
                    _probe(
                        window,
                        row["receiver_id"],
                        (_from_native(i, c) for i, c in enumerate(row["candidates"])),
                    )
                    for row in values.get("rows", ())
                ]
                return result, probes

            warm, saved = {}, {}
            for mode in MODES:
                result, probes = call(mode)
                warm[mode] = (result.status, probes)
                saved[mode] = []
            if warm["capture"][0] != warm["ordinary"][0]:
                raise ValueError("the matched capture validity decision changed")
            if warm["capture"][0] == "processed":
                for rep in range(3):
                    for mode in MODES if (index + rep) % 2 == 0 else MODES[::-1]:
                        wall, cpu = perf_counter_ns(), process_time_ns()
                        result, probes = call(mode)
                        elapsed = dict(
                            wall_ms=(perf_counter_ns() - wall) / 1e6,
                            cpu_ms=(process_time_ns() - cpu) / 1e6,
                        )
                        if warm[mode] != (result.status, probes):
                            raise ValueError("repeated frozen detector payload changed")
                        saved[mode].append(elapsed)
            state, traced, acquisition = trace_capture(window, policy)
            if (state, traced) != warm["capture"]:
                raise ValueError("tracing changed the deployed capture output")
            ordinary = [
                {
                    k: r[k]
                    for k in (
                        "receiver_id",
                        "retained_peak_count",
                        "coarse_gate_skipped_count",
                        "candidates",
                    )
                }
                for r in values.get("rows", ())
            ]
            row = dict(
                visit=window.acquisition["global_visit"],
                sequence=window.sequence,
                segment=segment,
                iq_sha256=window.iq_sha256,
                status=state,
                capture=warm["capture"][1],
                ordinary=warm["ordinary"][1],
                capture_acquisition=acquisition,
                ordinary_candidates=ordinary,
                timings=saved,
            )
            if state == "processed" and intervention is None:
                status, probes, calls = trace_capture(window, policy, shrink=True)
                intervention = dict(
                    visit=row["visit"],
                    status=status,
                    capture_cfo_intersection=probes,
                    acquisition=calls,
                    original_capture=traced,
                    ordinary=warm["ordinary"][1],
                )
            rows.append(row)
    return dict(
        id=case_id,
        provenance=provenance,
        decode_ms=decode,
        rows=rows,
        only_cfo_domain_changed=intervention,
    )


def keyed_rows(probes):
    mapping = {(r["visit_index"], r["receiver_id"]): r for r in probes}
    if len(mapping) != len(probes):
        raise ValueError("a physical probe was duplicated")
    return mapping


def compare_rows(left, right):
    a, b = keyed_rows(left), keyed_rows(right)
    if a.keys() != b.keys():
        raise ValueError("fresh detector omitted or reordered physical support")
    reasons = {}
    for key in a:
        p, q = a[key], b[key]
        if {k: v for k, v in p.items() if k != "candidates"} != {
            k: v for k, v in q.items() if k != "candidates"
        }:
            raise ValueError("two probe records have incompatible physical support")
        if encoded(p) != encoded(q):
            for x, y in zip(p["candidates"], q["candidates"], strict=False):
                for field in x:
                    if encoded(x[field]) != encoded(y[field]):
                        reasons[field] = reasons.get(field, 0) + 1
            if len(p["candidates"]) != len(q["candidates"]):
                reasons["candidate_count"] = reasons.get("candidate_count", 0) + 1
    return dict(
        probes=len(a),
        exact=sum(encoded(a[k]) == encoded(b[k]) for k in a),
        differing_fields=reasons,
        candidate_count=[sum(len(r["candidates"]) for r in p.values()) for p in (a, b)],
    )


def locked_native(case, mode):
    if mode == "capture":
        loc = case["native"]
        return BULK / loc["path"], loc["sha256"]
    ident = case["id"]
    folder = SCREEN / (
        "streamlined/whole-fractional" if ident in (CASES[0], CASES[2]) else "next/full-held-pair"
    )
    lock_path = folder / "source-lock.json"
    lock = json.loads((folder / "prediction-lock.json").read_bytes())
    ledger = json.loads(lock_path.read_bytes())
    if lock.get("source_lock_sha256") != _sha(lock_path):
        raise ValueError("prior ordinary authority differs from the sealed source lock")
    entry = ledger["inputs"][ident]
    digest = json.loads(ORDINARY.read_bytes())["recordings"][ident]["native_sha256"]
    if entry["native_sha256"] != digest:
        raise ValueError("two ordinary factor authorities disagree")
    return Path(entry["stock_lane_path"]) / "native.json", digest


def compare():
    summary = {}
    for ident in CASES:
        path = REPORT / f"{ident}.json.gz"
        trial = json.loads(gzip.decompress(path.read_bytes()))
        case = _load_case(ident)
        visited = {r["visit"] for r in trial["rows"]}
        observed = {mode: [p for r in trial["rows"] for p in r[mode]] for mode in MODES}
        comparison = dict(
            replay_sha256=_sha(path),
            provenance=trial["provenance"],
            admitted=sum(r["status"] == "processed" for r in trial["rows"]),
            excluded=sum(r["status"] != "processed" for r in trial["rows"]),
            cross_detector=compare_rows(*observed.values()),
        )
        for mode in MODES:
            ref, sha = locked_native(case, mode)
            if _sha(ref) != sha:
                raise ValueError("stored detector output differs from its frozen digest")
            archived = json.loads(ref.read_bytes())
            src = archived["source"]
            if src["session_id"] != case["session_id"]:
                raise ValueError("stored detector factors belong to another recording")
            expected_excluded = {
                (r["visit"], r["iq_sha256"])
                for r in archived["provenance"]["excluded_windows"]
                if r["visit"] in visited
            }
            observed_excluded = {
                (r["visit"], r["iq_sha256"]) for r in trial["rows"] if r["status"] != "processed"
            }
            if expected_excluded != observed_excluded:
                raise ValueError("stored and fresh capture exclusions disagree")
            reference = [p for p in src["probes"] if p["visit_index"] in visited]
            clocks = [t for row in trial["rows"] for t in row["timings"][mode]]
            comparison[mode] = dict(
                archive_sha256=sha,
                archive=str(ref),
                comparison=compare_rows(observed[mode], reference),
                calls=len(clocks),
                wall_median_ms=median(r["wall_ms"] for r in clocks),
                cpu_median_ms=median(r["cpu_ms"] for r in clocks),
            )
        diagnostic = trial["only_cfo_domain_changed"]
        comparison["only_cfo_domain_changed"] = dict(
            visit=diagnostic["visit"],
            changed_from_capture=compare_rows(
                diagnostic["capture_cfo_intersection"], diagnostic["original_capture"]
            ),
            against_ordinary=compare_rows(
                diagnostic["capture_cfo_intersection"], diagnostic["ordinary"]
            ),
        )
        summary[ident] = comparison
    save_json(REPORT / "comparison.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=(*CASES, "compare"))
    args = parser.parse_args()
    if args.action == "compare":
        compare()
    else:
        payload = replay(args.action)
        write(
            local_output(REPORT / f"{args.action}.json.gz"),
            gzip.compress(encoded(payload), mtime=0),
        )
