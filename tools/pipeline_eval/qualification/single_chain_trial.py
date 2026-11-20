"""Qualify physical one-receiver ordinary GLRT on sealed roof recordings."""

import argparse
import json
import os
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from statistics import median
from time import perf_counter, process_time

from ..__main__ import local_output
from ..scoring import ARMS, distance_km, validate_result
from ..variants import single_chain, v5_lean
from .full_v5_check import BULK, FROZEN, NATIVE_LIBRARY, _from_native, _load_case, _sha
from .recording_to_v5 import RECORDING_EDGES, bind_request, digest, save

COMPLETE = BULK / "leo-dev/pipeline-eval-20261118/full-v5-check"
NATIVE_INPUTS = {
    "DS26-0036": (
        COMPLETE / "native-complete/native.json",
        "41b74326231d17abcc1ed6e8cfd37574a2f5752c366bc1e8b959c39c1ec5f94e",
    ),
    "DS29-0082": (
        COMPLETE / "native-complete-ds29/native.json",
        "9b66406e24a94f2cf11adfe858289dbd45696d4e1244d5374b5679d32e8bec49",
    ),
}
PROJECTIONS = ("capture-era-rx0", "ordinary-native-rx0")
DUAL = ("capture-era-dual", "ordinary-native-dual")
RECEIVER_SENSITIVITY = ("capture-era-rx1", "ordinary-native-rx1")
FACTOR_BOUNDARIES = {
    "capture-era": "Stored capture-era GLRT factors to frozen no-repair v5",
    "ordinary-native": "Archived ordinary native GLRT factors to frozen no-repair v5",
}
WAVEFORM_SEGMENTS = (0, 8)
WAVEFORM_REPEATS = 3


def read(path, expected):
    payload = path.read_bytes()
    if sha256(payload).hexdigest() != expected:
        raise ValueError(f"artifact digest does not match the frozen input: {path}")
    return json.loads(payload)


def archive(case_id, producer):
    case = _load_case(case_id)
    locator = case["native"]
    path, expected = (
        (BULK / locator["path"], locator["sha256"])
        if producer == "capture-era"
        else NATIVE_INPUTS[case_id]
    )
    document = read(path, expected)
    if (
        document["source"]["session_id"] != case["session_id"]
        or document["provenance"]["window_count"] != case["recording"]["window_count"]
    ):
        raise ValueError("factor document does not bind the selected complete recording")
    return case, path, expected, document


def factor_summary(document):
    source, provenance = document["source"], document["provenance"]
    rows = source["probes"]
    support = {}
    for row in rows:
        identity = row["receiver_id"], row["channel"]
        counts = support.setdefault(identity, dict(probes=0, candidates=0, positive=0))
        counts["probes"] += 1
        counts["candidates"] += len(row["candidates"])
        counts["positive"] += sum(c["passed_fractional_margin_gate"] for c in row["candidates"])
    if set(support) != {(rx, ch) for rx in (0, 1) for ch in range(1, 9)}:
        raise ValueError(
            "factor input does not retain both physical receivers and all eight channels"
        )
    return dict(
        recording_windows=provenance["window_count"],
        processed_windows=provenance["processed_windows"],
        invalid_capture=provenance["invalid_capture"],
        probe_rows=len(rows),
        analysis_manifest_sha256=source["analysis_manifest_sha256"],
        raw_recording_authority_digest=source["raw_recording_authority_digest"],
        receiver_channels=[
            dict(receiver=rx, channel=ch, **counts) for (rx, ch), counts in sorted(support.items())
        ],
    )


def run_factor(case_id, destination, variant):
    destination = local_output(destination)
    producer, lane = variant.rsplit("-", 1)
    case, path, reference_sha, document = archive(case_id, producer)
    destination.mkdir(parents=True, exist_ok=False)
    if lane != "dual":
        document = single_chain.project_document(document, int(lane[-1]))
        path = destination / "native.json"
        save(path, document)
    summary = factor_summary(document)
    experiment = bind_request(case, path, destination / "experimental-request.json")
    began = perf_counter()
    result = v5_lean.run(experiment, destination / "position")
    result["boundary"] = FACTOR_BOUNDARIES[producer]
    if lane != "dual":
        result["boundary"] += f" using only physical {lane.upper()} factors"
    validate_result(result)
    data = dict(
        id=case_id,
        variant=variant,
        base_factor_sha256=reference_sha,
        inference_factor_sha256=_sha(path),
        factor_summary=summary,
        cpu=min(os.sched_getaffinity(0)),
        result=result,
        worker_wall_s=perf_counter() - began,
    )
    save(destination / "prediction.json", data)
    return data


def compare_measurement(reference, fresh):
    """Require the original support and count exact retained candidate disagreements."""
    source = reference["source"]
    if (
        any(
            fresh[key] != reference[key]
            for key in ("clock_anchor", "delivery_clocks", "last_sample_counter")
        )
        or any(
            fresh["source"][key] != val
            for key, val in source.items()
            if key not in ("analysis_manifest_sha256", "probes")
        )
        or any(
            fresh["provenance"][key] != reference["provenance"][key]
            for key in ("window_count", "processed_windows", "invalid_capture", "excluded_windows")
        )
    ):
        raise ValueError("fresh replay and archived factor recording authorities differ")
    mismatches = []
    measured_probes = measured_candidates = 0
    for archived, measured in zip(source["probes"], fresh["source"]["probes"], strict=True):
        identity = {key: value for key, value in archived.items() if key != "candidates"}
        if identity != {key: value for key, value in measured.items() if key != "candidates"}:
            raise ValueError("fresh factors changed the recorded probe identity")
        if identity["receiver_id"] == 0:
            measured_probes += 1
            measured_candidates += len(measured["candidates"])
            if archived["candidates"] != measured["candidates"]:
                mismatches.append(
                    dict(
                        visit=identity["visit_index"],
                        channel=identity["channel"],
                        archived_sha256=digest(archived["candidates"]),
                        fresh_sha256=digest(measured["candidates"]),
                    )
                )
        elif identity["receiver_id"] != 1 or measured["candidates"]:
            raise ValueError("fresh RX0 replay must leave the physical RX1 probe slot empty")
    return dict(
        measured_probes=measured_probes,
        measured_candidates=measured_candidates,
        exact_measured_probes=measured_probes - len(mismatches),
        candidate_list_mismatches=mismatches,
    )


def collect_raw(case_id, recording, projected_receipt):
    """Bind the complete fresh IQ evidence to the archived native RX0 projection."""
    _, _, expected, reference = archive(case_id, "ordinary-native")
    fresh_path = recording / "native.json"
    fresh = json.loads(fresh_path.read_bytes())
    if (
        fresh["provenance"].get("detector_mode") != "single-rx0"
        or fresh["provenance"]["detector_sha256"] != reference["provenance"]["detector_sha256"]
    ):
        raise ValueError("comparison requires the same native binary on the genuine RX0 path")
    receipt = json.loads((recording / "predictions.jsonl").read_bytes())
    projected = json.loads(projected_receipt.read_bytes())
    job = json.loads((recording / "experimental-request.json").read_bytes())["job"]
    fresh_sha = _sha(fresh_path)
    if (
        receipt["id"] != case_id
        or projected["id"] != case_id
        or projected["variant"] != "ordinary-native-rx0"
        or projected["base_factor_sha256"] != expected
        or job["native_input"]["sha256"] != "sha256:" + fresh_sha
        or job["identity"]["session_id"] != fresh["source"]["session_id"]
    ):
        raise ValueError("position inputs do not bind the selected case and variant")
    for prediction in (receipt, projected):
        validate_result(prediction["result"])
    audit = compare_measurement(reference, fresh)
    same_positions = {
        arm: receipt["result"]["arms"][arm]["latlon"] == projected["result"]["arms"][arm]["latlon"]
        for arm in ARMS
    }
    return dict(
        receipt,
        variant="fresh-native-rx0",
        inference_factor_sha256=fresh_sha,
        base_factor_sha256=expected,
        factor_summary=factor_summary(fresh),
        archived_rx0_comparison=dict(audit, equal_position=same_positions),
    )


def waveform(case_id, library, mode):
    """Compare authenticated IQ at the native call boundary on one pinned CPU."""
    import numpy as np

    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    from ..variants.iq_stream import load_windows

    case, _, factor_sha, document = archive(case_id, "ordinary-native")
    source = document["source"]
    rate, edge = source["sample_rate_hz"], RECORDING_EDGES[case_id]
    windows = [
        (index, w)
        for index in WAVEFORM_SEGMENTS
        for w in load_windows(case, range(8), segment_index=index)
    ]
    for _, window in windows:
        if (
            window.receiver_ids != (0, 1)
            or window.sample_rate_hz != rate
            or window.target["edge"] != edge
        ):
            raise ValueError("selected IQ differs from frozen native detector geometry")
    selected = {w.acquisition["global_visit"] for _, w in windows}
    probes = {
        (probe["visit_index"], probe["receiver_id"]): probe["candidates"]
        for probe in source["probes"]
        if probe["visit_index"] in selected
    }
    excluded = {
        row["visit"]: row
        for row in document["provenance"]["excluded_windows"]
        if row["visit"] in selected
    }
    del source, document

    input_identity_before = _sha(library)
    exact = np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16")
    control = np.asarray(
        qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
    )
    active = ("dual", "rx0") if mode == "paired" else (mode,)
    rss_before = getrusage(RUSAGE_SELF).ru_maxrss
    rss_resident_before = resident_kib()
    rows, timings, setup = [], {name: [] for name in active}, {}
    with ExitStack() as stack:
        contexts = {}
        for name in active:
            start, cpu = perf_counter(), process_time()
            contexts[name] = stack.enter_context(
                NativeShortWindow(
                    str(library),
                    exact,
                    control,
                    sample_rate_hz=rate,
                    receiver_count=2 if name == "dual" else 1,
                    fractional_epoch=True,
                )
            )
            setup[name] = dict(wall_s=perf_counter() - start, cpu_s=process_time() - cpu)

        def run(arm, samples):
            native = contexts[arm]
            if arm == "dual":
                return native.analyze(samples, include_timings=True)
            return single_chain.analyze_native(native, samples, include_timings=True)

        warmup = next(w for _, w in windows if w.acquisition["global_visit"] not in excluded)
        for name in active:
            run(name, warmup.samples)
        for i, (segment, window) in enumerate(windows):
            visit = window.acquisition["global_visit"]
            row = dict(
                visit=visit,
                segment=segment,
                sequence=window.sequence,
                sample_start=window.acquisition["sample_start"],
                channel=window.target["channel"],
                iq_sha256=window.iq_sha256,
                status="processed",
            )
            if visit in excluded:
                exclusion = excluded[visit]
                if (
                    row["sample_start"] != exclusion["sample_start"]
                    or row["iq_sha256"] != exclusion["iq_sha256"]
                ):
                    raise ValueError("capture exclusion does not bind the authenticated visit")
                row.update(status="invalid_capture", reason=exclusion["reason"])
                rows.append(row)
                continue

            row.update(calls=[], equal_rx0=[], archive_agreement={name: [] for name in active})
            for repeat in range(WAVEFORM_REPEATS):
                order = active if (i + repeat) % 2 == 0 else active[::-1]
                outputs, measurement = {}, {}
                for name in order:
                    cpu, start = process_time(), perf_counter()
                    result = run(name, window.samples)
                    measurement[name] = dict(
                        wall_s=perf_counter() - start,
                        cpu_s=process_time() - cpu,
                        c_detector_cpu_ms=result["detector_cpu_ms"],
                    )
                    timings[name].append(measurement[name])
                    outputs[name] = [
                        {k: v for k, v in r.items() if k != "timings_ms"} for r in result["rows"]
                    ]
                    agreement = []
                    for lane in outputs[name]:
                        fresh = [
                            _from_native(rank, candidate)
                            for rank, candidate in enumerate(lane["candidates"])
                        ]
                        fresh = [candidate for candidate in fresh if candidate is not None]
                        agreement.append(fresh == probes[(visit, lane["receiver_id"])])
                    row["archive_agreement"][name].append(agreement)
                row["calls"].append(dict(order=order, measurement=measurement))
                if mode == "paired":
                    dual, one = outputs["dual"][0], outputs["rx0"][0]
                    row["equal_rx0"].append(dual == one)
                    if dual != one:
                        row.setdefault("disagreements", []).append(
                            dict(repeat=repeat, dual=dual, rx0=one)
                        )
                if repeat == 0:
                    row["candidates"] = {
                        name: [len(lane["candidates"]) for lane in lanes]
                        for name, lanes in outputs.items()
                    }
                    row["first_scientific_row_digests"] = {
                        name: [digest(lane) for lane in lanes] for name, lanes in outputs.items()
                    }
            rows.append(row)
        rss_resident_with_context = resident_kib()

    if _sha(library) != input_identity_before:
        raise ValueError("native detector binary changed during waveform replay")
    totals = {}
    for name in active:
        calls = timings[name]
        totals[name] = dict(
            calls=len(calls),
            detector_input_bytes_per_call=(rate // 50) * 4 * (2 if name == "dual" else 1),
            cpu_median_s=median(x["cpu_s"] for x in calls),
            wall_median_s=median(x["wall_s"] for x in calls),
            windows_per_wall_second=len(calls) / sum(x["wall_s"] for x in calls),
        )
    return dict(
        case_id=case_id,
        cpu=min(os.sched_getaffinity(0)),
        mode=mode,
        factor_sha256=factor_sha,
        library_sha256=input_identity_before,
        target_edge=edge,
        sample_rate_hz=rate,
        waveform_segments=WAVEFORM_SEGMENTS,
        repeats=WAVEFORM_REPEATS,
        rows=rows,
        setup=setup,
        timing=totals,
        archive_bytes_per_window=(rate // 50) * 8,
        peak_rss_before_context_kib=rss_before,
        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        resident_before_context_kib=rss_resident_before,
        resident_with_context_kib=rss_resident_with_context,
    )


def resident_kib():
    return next(
        int(line.split()[1])
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith("VmRSS:")
    )


def score(case_id, predictions):
    path = FROZEN / "targets.jsonl"
    expected = json.loads((FROZEN / "provenance.json").read_bytes())["files"][path.name]
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError("frozen scoring roster changed")
    truth = next(row["truth"] for row in map(json.loads, data.splitlines()) if row["id"] == case_id)
    scores = []
    for prediction in predictions:
        if prediction["id"] != case_id:
            raise ValueError("prediction belongs to a different recording")
        result, metrics = prediction["result"], prediction["result"]["metrics"]
        validate_result(result)
        scores.append(
            dict(
                variant=prediction["variant"],
                status=result["status"],
                reason=result.get("reason"),
                worker_wall_s=prediction["worker_wall_s"],
                native_observations=metrics.get("native_observations"),
                tracks=metrics.get("tracks"),
                arms={
                    arm: dict(
                        error_km=distance_km(result["arms"][arm]["latlon"], truth),
                        conditional_rms_hz=metrics.get(f"{arm}_conditional_rms_hz"),
                        conditional_frequency_score=metrics.get(f"{arm}_frequency_score"),
                    )
                    for arm in ARMS
                },
            )
        )
    return dict(case_id=case_id, scores=scores)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=NATIVE_INPUTS)
    parser.add_argument("--out", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    factor = commands.add_parser("factors")
    factor.add_argument("variants", nargs="+", choices=(*PROJECTIONS, *DUAL, *RECEIVER_SENSITIVITY))
    raw = commands.add_parser("waveform")
    raw.add_argument("--library", type=Path, default=NATIVE_LIBRARY)
    raw.add_argument("--mode", choices=("paired", "dual", "rx0"), default="paired")
    collect = commands.add_parser("collect-raw")
    collect.add_argument("recording", type=Path)
    collect.add_argument("projected_receipt", type=Path)
    scoring = commands.add_parser("score")
    scoring.add_argument("receipts", nargs="+", type=Path)
    args = parser.parse_args()
    args.out = local_output(args.out)
    if args.command == "factors":
        if len(os.sched_getaffinity(0)) != 1:
            parser.error("pin the factor comparison to one CPU")
        for variant in args.variants:
            row = run_factor(args.case, args.out / variant, variant)
            print(args.case, variant, row["result"]["status"], flush=True)
    elif args.command == "waveform":
        if len(os.sched_getaffinity(0)) != 1 or any(
            os.environ.get(k) != "1"
            for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
        ):
            parser.error("use one CPU and one numerical thread for the waveform comparison")
        save(args.out, waveform(args.case, args.library, args.mode))
    elif args.command == "collect-raw":
        save(args.out, collect_raw(args.case, args.recording, args.projected_receipt))
    else:
        rows = [json.loads(path.read_bytes()) for path in args.receipts]
        save(args.out, score(args.case, rows))


if __name__ == "__main__":
    main()
