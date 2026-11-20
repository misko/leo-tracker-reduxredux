"""Replay one complete frozen recording with native GLRT and the v5 position solver."""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, suppress
from hashlib import sha256
from pathlib import Path

from tools.pipeline_eval.qualification import capture_release
from tools.pipeline_eval.qualification.full_v5_check import (
    BULK,
    NATIVE_LIBRARY,
    PRODUCERS,
    REPO,
    _bind_producer,
    _from_native,
    _load_case,
    _probe,
    _sha,
)

CASE_ID = "DS26-0036"
MAXIMUM_SECONDS = 20 * 60
ARCHIVE_PYTHON = Path("/opt/leo-fast-auto/20261010-r1/venv/bin/python")
SINGLE_THREAD = {key: "1" for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")}
RECORDING_EDGES = {"DS26-0036": "lower", "DS29-0082": "upper"}
MODULE = "tools.pipeline_eval.qualification.recording_to_v5"
DETECTORS = ("ordinary", "single-rx0")


def encoded(value):
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def digest(value):
    return "sha256:" + sha256(encoded(value).encode()).hexdigest()


def stream_range(library, worker, segments, case_id, capture=None, detector="ordinary"):
    """Publish every authenticated visit and a completion receipt for each segment."""
    import numpy as np

    from leo.analysis.starlink.native_short_window import NativeShortWindow
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
    from leo.contracts.fast_scan import FastScanReceiverV1
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window
    from leo.storage.fast_scan import FastSegmentSource

    policy = FastScanPolicyV2()
    if detector not in DETECTORS:
        raise ValueError("unknown full recording detector")
    if capture is None:
        source_root = PRODUCERS[case_id].root
        edge = RECORDING_EDGES[case_id]
    else:
        case = capture["case"]
        producer = capture_release.producer(case, capture)
        if case["id"] != case_id or digest(segments) != capture["segments_sha256"]:
            raise ValueError("raw worker input differs from the sealed segments")
        _bind_producer(case, producer, policy)
        source_root = producer.root
        edge = capture["edge"]
    if not Path(analyze_window.__code__.co_filename).is_relative_to(source_root):
        raise ValueError("launch the raw worker with the recording's installed source runtime")
    rate = policy.sample_rate_hz
    exact = np.asarray(qin_edge_pilot_frame(rate, edge), dtype="<c16")
    control = np.asarray(
        qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL), dtype="<c16"
    )
    library_hash = "sha256:" + _sha(library)
    if detector == "single-rx0":
        from tools.pipeline_eval.variants.single_chain import analyze_native
    receiver_count = 1 if detector == "single-rx0" else 2
    with NativeShortWindow(
        str(library),
        exact,
        control,
        sample_rate_hz=rate,
        receiver_count=receiver_count,
        fractional_epoch=True,
    ) as native:
        for index in range(worker, len(segments), 2):
            locator = segments[index]
            manifest = (BULK / locator["path"]).resolve()
            if manifest.name != "manifest.json" or not manifest.is_relative_to(
                (BULK / "leo/fast-scan-recordings").resolve()
            ):
                raise ValueError("raw segment lies outside the recording archive")
            directory = manifest.parent
            source = FastSegmentSource(
                dict(path=str(directory), manifest_digest="sha256:" + locator["sha256"])
            )
            epoch_start = time.perf_counter()
            detector_cpu_s = 0.0
            count = 0
            if source.receiver_ids != (0, 1):
                raise ValueError("the frozen replay requires both recorded receivers")

            for window in source.windows():
                if window.target["edge"] != edge:
                    raise ValueError("recorded pilot edge differs from the replay template")
                acquisition = window.acquisition
                retune = json.loads(acquisition.get("retune_receipt") or "{}")
                probes = []

                def detect(window, receivers, probes=probes):
                    nonlocal detector_cpu_s
                    started = time.process_time()
                    output = (
                        analyze_native(native, window.samples, receiver_id=0)
                        if detector == "single-rx0"
                        else native.analyze(window.samples)
                    )
                    rows = output["rows"]
                    detector_cpu_s += time.process_time() - started
                    if tuple(row["receiver_id"] for row in rows) != tuple(range(receiver_count)):
                        raise ValueError("the native detector returned unexpected receiver IDs")
                    for row in rows:
                        probes.append(
                            _probe(
                                window,
                                receivers[row["receiver_id"]],
                                (_from_native(rank, c) for rank, c in enumerate(row["candidates"])),
                            )
                        )
                    if detector == "single-rx0":
                        probes.append(_probe(window, receivers[1], ()))
                    # The outer adapter only needs the measured receiver IDs for its
                    # capture-status contract. Fresh fractional candidates leave via probes.
                    return tuple(
                        FastScanReceiverV1(receiver_id=rx, candidates=()) for rx in receivers
                    )

                status = analyze_window(window, source.receiver_ids, None, policy, detector=detect)
                print(
                    encoded(
                        dict(
                            kind="visit",
                            segment=index,
                            sequence=window.sequence,
                            visit=int(acquisition["global_visit"]),
                            iq_sha256=window.iq_sha256,
                            sample_start=status.sample_start,
                            sample_end=status.sample_end,
                            generation=status.generation,
                            status=status.status,
                            reason=status.reason,
                            rf_mapping_authority=status.rf_mapping_authority,
                            probes=probes,
                            input_bytes=window.samples.nbytes,
                            clock_anchor=retune.get("utc_clock_bracket"),
                            delivery_clock=retune.get("host_delivery_clock"),
                        )
                    ),
                    flush=True,
                )
                count += 1
            print(
                encoded(
                    dict(
                        kind="segment",
                        segment=index,
                        count=count,
                        path=str(directory),
                        manifest_digest=source.manifest_digest,
                        radio_id=source.radio["serial"],
                        library_sha256=library_hash,
                        wall_s=time.perf_counter() - epoch_start,
                        detector_cpu_s=detector_cpu_s,
                        detector=detector,
                    )
                ),
                flush=True,
            )
            print(
                f"Segment {index} verified and replayed, {count} windows",
                file=sys.stderr,
                flush=True,
            )
    if "sha256:" + _sha(library) != library_hash:
        raise ValueError("native detector binary changed during the replay")
    print(encoded(dict(kind="worker", worker=worker)), flush=True)


def native_document(case, lanes, capture=None, detector="ordinary"):
    """Consolidate fully verified streams, retaining exclusions and empty receiver factors."""
    if detector not in DETECTORS:
        raise ValueError("unknown full recording detector")
    visits, segments = [], {}
    for worker, lane in enumerate(lanes):
        if not lane or lane[-1] != dict(kind="worker", worker=worker):
            raise ValueError(f"raw lane {worker} did not reach its verified terminal receipt")
        pending = []
        for row in lane[:-1]:
            if row["segment"] % 2 != worker:
                raise ValueError("segment appeared in the wrong raw lane")
            if row["kind"] == "visit":
                pending.append(row)
                continue
            index = row["segment"]
            if (
                row["kind"] != "segment"
                or index in segments
                or not pending
                or row["count"] != len(pending)
                or any(p["segment"] != index or p["sequence"] != i for i, p in enumerate(pending))
            ):
                raise ValueError("raw segment is incomplete or duplicated")
            segments[index] = row
            visits.extend(pending)
            pending.clear()
        if pending:
            raise ValueError("unverified segment at end of raw lane")

    recording = case["recording"]
    if set(segments) != set(range(len(recording["segments"]))):
        raise ValueError("raw stream omitted a frozen segment")
    inventory_segments = []
    for index, locator in enumerate(recording["segments"]):
        receipt = segments[index]
        if (
            receipt["manifest_digest"] != "sha256:" + locator["sha256"]
            or Path(receipt["path"]) != (BULK / locator["path"]).parent
        ):
            raise ValueError("raw segment receipt does not bind the frozen segment")
        inventory_segments.append(
            dict(
                scope=f"segment-{index:08d}",
                path=receipt["path"],
                manifest_digest=receipt["manifest_digest"],
                windows=receipt["count"],
            )
        )
    input_manifest = capture_release.inventory_digest(inventory_segments, recording["window_count"])
    producer = PRODUCERS[case["id"]] if capture is None else capture_release.producer(case, capture)
    if input_manifest != producer.input_manifest_sha256:
        raise ValueError("replayed manifest inventory does not reproduce the acquisition identity")

    visits.sort(key=lambda row: row["visit"])
    if len(visits) != recording["window_count"] or any(
        row["visit"] != i for i, row in enumerate(visits)
    ):
        raise ValueError("raw replay must include each global visit exactly once")
    generation = visits[0]["generation"]
    clocks, probes, invalid = [], [], []
    previous_end = visits[0]["sample_start"]
    for row in visits:
        if (
            row["generation"] != generation
            or type(row["sample_start"]) is not int
            or row["sample_start"] < previous_end
            or type(row["sample_end"]) is not int
            or row["sample_end"] < row["sample_start"]
            or row["delivery_clock"] is None
        ):
            raise ValueError("raw capture counter or clocks have a gap in authority")
        previous_end = row["sample_end"]
        clocks.append(row["delivery_clock"])
        if row["status"] == "invalid_capture" and not row["probes"]:
            invalid.append(
                {
                    key: row[key]
                    for key in ("visit", "reason", "iq_sha256", "sample_start", "sample_end")
                }
            )
        elif row["status"] == "processed" and [p["receiver_id"] for p in row["probes"]] == [0, 1]:
            if detector == "single-rx0" and row["probes"][1]["candidates"]:
                raise ValueError("unmeasured physical receiver must have an empty factor")
            if any(
                p["visit_index"] != row["visit"] or p["valid_start_counter"] != row["sample_start"]
                for p in row["probes"]
            ):
                raise ValueError("fresh probe differs from recorded sample authority")
            probes.extend(row["probes"])
        else:
            raise ValueError("each visit needs a valid pair of fresh probes or a capture exclusion")
    anchors = [row["clock_anchor"] for row in visits if row["clock_anchor"] is not None]
    if len(anchors) != 1 or anchors[0]["sample_counter"] != visits[0]["sample_start"]:
        raise ValueError("raw recording does not have exactly one initial UTC anchor")
    radio_ids = {row["radio_id"] for row in segments.values()}
    libraries = {row["library_sha256"] for row in segments.values()}
    if {row.get("detector", "ordinary") for row in segments.values()} != {detector}:
        raise ValueError("raw segment detector differs from the requested measurement")
    if len(radio_ids) != 1 or len(libraries) != 1:
        raise ValueError("raw replay changed radios or detector binaries")
    library_sha = libraries.pop()
    # Timings and worker order do not participate in the new inference identity.
    identity = "native-short-window-glrt/fractional-epoch"
    if detector == "single-rx0":
        from tools.pipeline_eval.variants import single_chain

        identity += "/single-rx0/" + _sha(Path(single_chain.__file__))
    analysis_sha = digest([identity, library_sha, input_manifest, probes, invalid])
    iq_hashes = [row["iq_sha256"] for row in visits]
    source = dict(
        session_id=case["session_id"],
        capture_mode="adaptive",
        sample_rate_hz=10_000_000,
        radio_id=radio_ids.pop(),
        stream_generation=f"continuous-iio-{generation:016x}",
        input_manifest_sha256=input_manifest,
        analysis_manifest_sha256=analysis_sha,
        raw_recording_authority_digest=digest([input_manifest, iq_hashes]),
        qualified=True,
        timing=None,
        probes=probes,
        probe_ms=20,
        capture_start_utc_ns=None,
        capture_end_utc_ns=None,
    )
    provenance = dict(
        run_id="replay-" + analysis_sha[7:39],
        window_count=len(visits),
        processed_windows=len(probes) // 2,
        invalid_capture=len(invalid),
        excluded_windows=invalid,
        skipped_fast_score=0,
        rf_mapping_authorities=sorted({row["rf_mapping_authority"] for row in visits}),
        scope="fresh native fractional GLRT on the complete sealed recording",
        detector_sha256=library_sha,
    )
    if detector != "ordinary":
        provenance["scope"] = "fresh fractional GLRT on physical receiver zero at every valid visit"
        provenance["detector_mode"] = detector
    metrics = dict(
        recording_windows=len(visits),
        window_delivery_span_s=(clocks[-1]["monotonic_ns"] - clocks[0]["monotonic_ns"]) / 1e9,
        iq_bytes=sum(row["input_bytes"] for row in visits),
        processed_windows=len(probes) // 2,
        invalid_capture=len(invalid),
        probe_rows=len(probes),
        empty_probe_rows=sum(not p["candidates"] for p in probes),
        candidate_rows=sum(len(p["candidates"]) for p in probes),
        positive_candidates=sum(
            c["passed_fractional_margin_gate"] for p in probes for c in p["candidates"]
        ),
        detector_cpu_s=sum(row["detector_cpu_s"] for row in segments.values()),
    )
    return dict(
        schema_version=2,
        source=source,
        clock_anchor=anchors[0],
        delivery_clocks=clocks,
        last_sample_counter=visits[-1]["sample_end"],
        provenance=provenance,
    ), metrics


def save(path, value):
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        staged = Path(stream.name)
        try:
            stream.write(encoded(value) + "\n")
            stream.flush()
            os.link(staged, path)
        finally:
            staged.unlink()


def bind_request(case, native_path, request_out):
    """Keep the original truth-free v5 settings and bind the new numerical input."""
    locator = case["request"]
    original = BULK / locator["path"]
    if _sha(original) != locator["sha256"]:
        raise ValueError("frozen no-repair request has changed")
    request = json.loads(original.read_bytes())
    job = request["job"]
    if (
        request["role"] != "baseline"
        or job["evaluation_reference"] is not None
        or job["identity"]["session_id"] != case["session_id"]
        or job["native_input"]["sha256"] != "sha256:" + case["native"]["sha256"]
    ):
        raise ValueError("input is not the frozen blind baseline request")
    fresh_sha = "sha256:" + _sha(native_path)
    job["native_input"] = dict(path=str(native_path), sha256=fresh_sha)
    job["identity"].update(input_sha256=fresh_sha, run_id="experiment-" + fresh_sha[7:39])
    job["output_root"] = str(request_out.parent / "position")
    save(request_out, request)
    return dict(
        id=case["id"],
        panel=case["panel"],
        regions=case["regions"],
        session_id=case["session_id"],
        native_path=str(native_path),
        native_sha256=fresh_sha,
        request_path=str(request_out),
    )


def fit(directory, case_id=CASE_ID, deadline_s=MAXIMUM_SECONDS, detector="ordinary"):
    from tools.pipeline_eval.variants import v5_lean

    if not 1 <= deadline_s <= MAXIMUM_SECONDS:
        raise ValueError("the whole-recording budget must be at most 1,200 seconds")
    if directory.is_relative_to("/mnt/qnap01") or directory.is_relative_to(BULK / "leo"):
        raise ValueError("the replay output must be outside the recording archive")
    started = float((directory / "started_unix_s").read_text())
    phase = "raw input assembly"
    metrics = {}
    stage = {}
    try:
        case = _load_case(case_id)
        exits = directory / "raw-worker-exits.json"
        if exits.exists() and json.loads(exits.read_bytes())["exit_codes"] != [0, 0]:
            raise ValueError("both raw workers must finish successfully")
        lanes = []
        for worker in (0, 1):
            with (directory / f"replayed-{worker}.jsonl").open() as stream:
                lanes.append(list(map(json.loads, stream)))
        receipt = directory / "capture.json"
        capture = json.loads(receipt.read_bytes()) if receipt.exists() else None
        document, metrics = native_document(case, lanes, capture, detector)
        native_path = directory / "native.json"
        save(native_path, document)
        stage["raw_and_assembly_wall_s"] = time.time() - started
        experiment = bind_request(case, native_path, directory / "experimental-request.json")
        phase = "frozen v5 inference"
        print(
            f"Complete recording verified. Fitting v5 on {metrics['probe_rows']} probe rows.",
            flush=True,
        )
        remaining = int(deadline_s - (time.time() - started))
        if remaining <= 0:
            raise TimeoutError("whole-recording budget exhausted before inference")
        original_timeout = v5_lean.TIMEOUT_S
        try:
            v5_lean.TIMEOUT_S = remaining
            result = v5_lean.run(experiment, directory / "position")
        finally:
            v5_lean.TIMEOUT_S = original_timeout
    except Exception as error:
        result = dict(
            status="failed",
            reason=f"{phase}: {error}",
            metrics={},
            arms={"c0": {"latlon": None}, "fitted_c": {"latlon": None}},
        )
    result["boundary"] = "Complete recorded IQ to native GLRT and frozen no-repair v5 position"
    if detector == "single-rx0":
        result["boundary"] = "Complete recorded IQ, physical RX0 fractional GLRT and no-repair v5"
    result["metrics"].update(metrics, **stage)
    elapsed = time.time() - started
    if metrics.get("window_delivery_span_s", 0) > 0:
        result["metrics"]["replay_wall_over_recorded_span"] = (
            elapsed / metrics["window_delivery_span_s"]
        )
    save(
        directory / "predictions.jsonl",
        dict(id=case_id, result=result, worker_wall_s=elapsed),
    )
    print(result["status"], result.get("reason", ""), flush=True)
    return result


def run_recording(
    case_id,
    output_dir,
    cpus,
    deadline_s=MAXIMUM_SECONDS,
    native_library=NATIVE_LIBRARY,
    detector="ordinary",
    *,
    finish=None,
):
    """Run the whole recording with two raw workers and one v5 worker."""
    if detector not in DETECTORS or not 1 <= deadline_s <= MAXIMUM_SECONDS:
        raise ValueError("select a supported detector and a bounded elapsed time")
    available = os.sched_getaffinity(0)
    if len(cpus) != 2 or len(set(cpus)) != 2 or not set(cpus) <= available:
        raise ValueError("two distinct available CPUs are required")
    output = Path(output_dir).resolve()
    if output.is_relative_to("/mnt/qnap01") or output.is_relative_to(BULK / "leo"):
        raise ValueError("the replay output must be outside the recording archive")
    native_library = Path(native_library).resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    (output / "started_unix_s").write_text(f"{started}\n")
    case = _load_case(case_id)
    capture = capture_release.read_capture(case)
    capture.update(
        case={key: case[key] for key in ("id", "run_id", "session_id")},
        segments_sha256=digest(case["recording"]["segments"]),
    )
    root = capture_release.producer(case, capture).root
    save(output / "capture.json", capture)
    save(output / "segments.json", case["recording"]["segments"])
    children = []
    with ExitStack() as files:
        try:
            for worker, cpu in enumerate(cpus):
                source = files.enter_context((output / "segments.json").open("rb"))
                data = files.enter_context((output / f"replayed-{worker}.jsonl").open("xb"))
                log = files.enter_context((output / f"replayed-{worker}.log").open("xb"))
                command = [
                    "taskset",
                    "-c",
                    str(cpu),
                    "sudo",
                    "-n",
                    "-u",
                    "leo",
                    "--",
                    "env",
                    f"PYTHONPATH={root}:{REPO}",
                    *(f"{name}={value}" for name, value in SINGLE_THREAD.items()),
                    str(ARCHIVE_PYTHON),
                    "-Bu",
                    "-m",
                    MODULE,
                    str(worker),
                    "--case",
                    case_id,
                    "--native-library",
                    str(native_library),
                    "--capture",
                    encoded(capture),
                    "--detector",
                    detector,
                ]
                children.append(
                    subprocess.Popen(
                        command,
                        cwd=REPO,
                        stdin=source,
                        stdout=data,
                        stderr=log,
                        start_new_session=True,
                    )
                )
            for child in children:
                child.wait(timeout=max(0, min(650, deadline_s) - (time.time() - started)))
        except subprocess.TimeoutExpired:
            print("Raw replay reached its deadline. Keeping the partial receipts.", flush=True)
        except OSError as error:
            print(f"Raw worker could not start: {error}", flush=True)
        finally:
            for child in children:
                if child.poll() is None:
                    with suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        with suppress(ProcessLookupError):
                            os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
    save(
        output / "raw-worker-exits.json",
        dict(cpus=list(cpus), exit_codes=[p.returncode for p in children]),
    )
    os.sched_setaffinity(0, {cpus[0]})
    try:
        return (fit if finish is None else finish)(output, case_id, deadline_s, detector)
    finally:
        os.sched_setaffinity(0, available)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worker", type=int, nargs="?", choices=(0, 1))
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--fit", type=Path)
    action.add_argument("--replay", type=Path)
    parser.add_argument("--case", default=CASE_ID)
    parser.add_argument("--capture", type=json.loads)
    parser.add_argument("--detector", choices=DETECTORS, default="ordinary")
    parser.add_argument("--cpus", type=int, nargs=2)
    parser.add_argument("--deadline", type=int, default=MAXIMUM_SECONDS)
    parser.add_argument("--native-library", type=Path, default=NATIVE_LIBRARY)
    args = parser.parse_args()
    if args.replay is not None:
        if args.worker is not None or args.cpus is None:
            parser.error("replay requires two CPU numbers and no raw worker index")
        result = run_recording(
            args.case, args.replay, args.cpus, args.deadline, args.native_library, args.detector
        )
        raise SystemExit(int(result["status"] in ("failed", "timed_out", "unavailable")))
    if len(os.sched_getaffinity(0)) != 1 or any(
        os.environ.get(key) != "1" for key in SINGLE_THREAD
    ):
        parser.error("use one CPU of affinity and one thread per BLAS runtime")
    if args.fit is not None and args.worker is None:
        fit(args.fit.resolve(strict=True), args.case, args.deadline, args.detector)
    elif args.worker is not None and args.fit is None:
        stream_range(
            args.native_library.resolve(strict=True),
            args.worker,
            json.load(sys.stdin),
            args.case,
            args.capture,
            args.detector,
        )
    else:
        parser.error("choose one raw worker or --fit")


if __name__ == "__main__":
    main()
