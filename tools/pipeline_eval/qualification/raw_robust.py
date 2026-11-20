"""Authenticate whole IQ recordings, reconstruct anonymous tracks, then fit robust EM."""

import argparse
import gzip
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, references, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import v5_lean
from . import recording_to_v5, robust_em_trials
from .full_v5_check import BULK, NATIVE_LIBRARY, REPO, _load_case, _sha
from .prefix_figures import TIMING_IDS, csv_file

RAW_CASES = ("DS26-0036", "DS29-0082")
RAW_DEADLINE_S = 660
METHOD = "raw_robust"
BOUNDARY = "Complete native GLRT, fresh anonymous graph tracks and causal-TLE robust EM"
REPORT = REPO / "reports/2026_11_19_short_receiver"
ORDINARY_RECEIPT = REPO / "reports/2026_11_19_receiver_frontend/ordinary/recording-receipts.json"
OLD_SCRATCH = Path("/tmp/leo-complete-frontend-20261119/ordinary")
PRIOR_RAW = BULK / "leo-dev/pipeline-eval-20261118/full-v5-check"
PRIOR_NAMES = {"DS26-0036": "native-complete", "DS29-0082": "native-complete-ds29"}
DETECTORS = ("ordinary-native", "capture-era")
TRACK_WORKER = "tools.pipeline_eval.qualification.raw_robust_worker"
POSITION_FILES = ("positions.jsonl.gz", "control-positions.jsonl.gz")


def _check(path, checksum):
    if _sha(path) != checksum:
        raise ValueError(f"replay input differs from its hash: {path.name}")
    return path


def _complete_case(case_id):
    try:
        case = _load_case(case_id)
    except StopIteration as error:
        raise ValueError("recording is absent from the frozen input roster") from error
    if not all(
        isinstance(case.get(key), dict) and {"path", "sha256"} <= case[key].keys()
        for key in ("native", "catalog", "track_config")
    ) or not isinstance(case.get("recording"), dict):
        raise ValueError("receiver requires a complete native GLRT archive and frozen track config")
    return case


@cache
def locked_sources():
    files = {
        str(p.relative_to(v5_lean.SOURCE)): "sha256:" + _sha(p)
        for p in sorted((v5_lean.SOURCE / "leo").rglob("*"))
        if p.is_file() and p.suffix in (".py", ".so", ".h", ".c", ".inc")
    }
    frozen = recording_to_v5.digest(files)
    if frozen != v5_lean.SOURCE_SHA256:
        raise ValueError("frozen tracker source tree changed")
    fit = robust_em_trials.source_hashes()
    if fit != json.loads((REPORT / "robust-em/source-lock.json").read_bytes()):
        raise ValueError("robust EM differs from the pre-scoring source lock")
    return dict(frozen_tracker=frozen, robust_em=fit)


def prior_directory(case_id):
    if case_id in PRIOR_NAMES:
        return PRIOR_RAW / PRIOR_NAMES[case_id]
    return OLD_SCRATCH / case_id


def bind_detector(case, detector, native_directory):
    case_id = case["id"]
    if detector == "capture-era":
        if native_directory is not None:
            raise ValueError("capture-era detector comes from the published frozen native input")
        locator = case["native"]
        return (
            _check(BULK / locator["path"], locator["sha256"]),
            locator["sha256"],
            dict(source="frozen capture-era GLRT artifact", replayed_here=False),
        )
    if detector != "ordinary-native":
        raise ValueError("unknown whole-recording detector")
    directory = prior_directory(case_id) if native_directory is None else Path(native_directory)
    native = directory / "native.json"
    receipts = json.loads(ORDINARY_RECEIPT.read_bytes())["recordings"]
    expected = receipts[case_id]
    fresh_receipt = directory / "raw-receipt.json"
    if fresh_receipt.is_file():
        fresh_data = json.loads(fresh_receipt.read_bytes())
        if (
            fresh_data["id"] != case_id
            or fresh_data["raw_gate"] != "fresh whole-recording native GLRT"
            or fresh_data["recording_windows"] != case["recording"]["window_count"]
            or fresh_data["detector_sha256"] != expected["detector_sha256"]
            or fresh_data["native_input_manifest_sha256"] != expected["input_manifest_sha256"]
        ):
            raise ValueError("invalid fresh native replay authority")
        checksum = fresh_data["native_sha256"]
        return (
            _check(native, checksum),
            checksum,
            dict(
                source="fresh whole-recording ordinary native IQ replay",
                replayed_here=True,
                exact_prior_native=checksum == expected["native_sha256"],
                **fresh_data,
            ),
        )
    checksum = expected["native_sha256"]
    return (
        _check(native, checksum),
        checksum,
        dict(
            source="previously authenticated whole-recording ordinary native GLRT artifact",
            replayed_here=False,
            exact_prior_native=True,
            detector_sha256=expected["detector_sha256"],
            native_input_manifest_sha256=expected["input_manifest_sha256"],
        ),
    )


def compare_projection(fresh, published):
    meta = {name: fresh[name] == published[name] for name in fresh if name != "tracks"}

    def key(track):
        return track["receiver"], track["channel"], track["rf_hz"], tuple(track["times"])

    measured = {key(track): track["values"] for track in fresh["tracks"]}
    archived = {key(track): track["values"] for track in published["tracks"]}
    keys = measured.keys() & archived.keys()
    delta = max(
        (abs(a - b) for k in keys for a, b in zip(measured[k], archived[k], strict=True)),
        default=0.0,
    )
    return dict(
        exact_document=fresh == published,
        exact_clock_and_catalogue=all(meta.values()),
        fresh_tracks=len(fresh["tracks"]),
        published_tracks=len(published["tracks"]),
        same_lanes_and_timestamps=len(keys),
        same_lanes_timestamps_and_cfo=sum(measured[k] == archived[k] for k in keys),
        largest_matched_cfo_difference_hz=delta,
    )


def build_tracks(case, native, checksum, cpu):
    config = case["track_config"]
    request = dict(
        native=dict(path=str(native), sha256=checksum),
        track_config=dict(path=str(BULK / config["path"]), sha256=config["sha256"]),
        session_id=case["session_id"],
        window_count=case["recording"]["window_count"],
        cutoff_utc_ns=case["cutoff_utc_ns"],
        catalog_timestamp_ns=case["catalog_timestamp_ns"],
    )
    environment = {
        **os.environ,
        **recording_to_v5.SINGLE_THREAD,
        "PYTHONPATH": f"{v5_lean.SOURCE}:{REPO}",
    }
    command = [
        "taskset",
        "-c",
        str(cpu),
        str(v5_lean.PYTHON),
        "-B",
        "-m",
        TRACK_WORKER,
        "--frozen",
        str(v5_lean.SOURCE),
    ]
    process = subprocess.run(
        command,
        input=encoded(request),
        capture_output=True,
        env=environment,
        timeout=120,
        check=True,
    )
    return json.loads(process.stdout)


def _fit(packet, cpu):
    start = perf_counter()
    process = subprocess.run(
        robust_em_trials.sandbox(cpu),
        input=encoded(packet),
        capture_output=True,
        timeout=90,
        check=True,
    )
    return json.loads(process.stdout), perf_counter() - start


def _frozen_port(case, work):
    issues = {}
    graph = case.get("graph")
    if graph:
        graph_path = _check(BULK / graph["path"], graph["sha256"])
        observed = corpus._observation(case, graph_path, work, issues)
    else:
        root = Path(os.environ.get("PIPELINE_EVAL_BLIND_ROOT", corpus.DEFAULT_BLIND))
        observed = corpus._portable_input(
            root / case["blind_tree"], work, "observation", case["observation"], issues
        )
    if observed is None:
        raise ValueError(f"published track projection is unavailable for audit: {issues}")
    return json.loads(observed.read_bytes())


def predict(case_id, detector, work, cpu, native_directory=None):
    """Use only fresh graph tracks for the fit, then audit against the archive if applicable."""
    started = perf_counter()
    case = _complete_case(case_id)
    binding = locked_sources()
    native, checksum, acquisition = bind_detector(case, detector, native_directory)
    catalogue = case["catalog"]
    elements = _check(BULK / catalogue["path"], catalogue["sha256"]).read_text("ascii")
    (offer,) = case["regions"]
    if offer["center"] != list(v5_lean.ROOF_CENTER) or offer.get("width_km", 25) != 25:
        raise ValueError("the complete receiver uses the frozen single 25 km tile")
    graph = build_tracks(case, native, checksum, cpu)
    observation = graph["projection"]
    packet = dict(observation=observation, catalogue=elements, offer=offer)
    fitted, fit_wall = _fit(packet, cpu)
    result = fitted.pop("result")
    result["boundary"] = BOUNDARY
    fit_binding = sha256(encoded(packet)).hexdigest()
    observed_digest = sha256(corpus._packed(observation)).hexdigest()
    metrics = result["metrics"]
    metrics.update(
        graph["metrics"],
        fit_wall_s=fit_wall,
        fit_cpu_s=fitted["worker_cpu_s"],
        fit_peak_rss_kib=fitted["max_rss_kib"],
    )
    numerical_wall = perf_counter() - started
    audit = None
    if detector == "capture-era":
        try:
            expected = _frozen_port(case, work / "comparison-only")
        except (OSError, ValueError) as error:
            audit = dict(status="unavailable", reason=str(error))
        else:
            audit = dict(status="compared", **compare_projection(observation, expected))
        audit.update(projected_sha256=observed_digest, frozen_sha256=case.get("observation"))
    if robust_em_trials.source_hashes() != binding["robust_em"]:
        raise ValueError("robust EM source changed during the fit")
    validate_result(result)
    row = dict(
        id=case_id,
        method=METHOD,
        detector=detector,
        mode="matched-tile",
        variant="fresh-iq" if acquisition["replayed_here"] else detector + "-artifact",
        cpu=cpu,
        input_sha256=fit_binding,
        native_sha256=checksum,
        catalog_sha256=catalogue["sha256"],
        observation_sha256=observed_digest,
        tile=offer,
        implementation_sha256=binding["robust_em"]["robust_em.py"],
        track_config_sha256=case["track_config"]["sha256"],
        tracker_source_sha256=binding["frozen_tracker"],
        acquisition=acquisition,
        capture_authority=graph["authority"],
        projection_audit=audit,
        worker_wall_s=numerical_wall,
        worker_cpu_s=fitted["worker_cpu_s"],
        max_rss_kib=max(fitted["max_rss_kib"], metrics["track_peak_rss_kib"]),
        result=result,
    )
    save_json(work / detector / f"{case_id}.json", row)
    print(
        case_id,
        detector,
        result["status"],
        f"tracks={metrics['tracks']} fit={fit_wall:.2f}s",
        flush=True,
    )
    return row


def run(case, work_dir, *, detector="capture-era", native_directory=None):
    """Pipeline-evaluation entry point for a frozen roof recording."""
    try:
        row = predict(
            case.get("id"),
            detector,
            local_output(work_dir),
            min(os.sched_getaffinity(0)),
            native_directory,
        )
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        return dict(
            status="unavailable",
            boundary=BOUNDARY,
            reason=str(error),
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        )
    return dict(
        row["result"],
        input_binding={
            key: row[key]
            for key in (
                "input_sha256",
                "native_sha256",
                "catalog_sha256",
                "track_config_sha256",
                "observation_sha256",
                "tracker_source_sha256",
                "capture_authority",
                "tile",
            )
        },
    )


def replay_batch(work, cpus, detector, cases, fresh_root=None):
    if len(cpus) != len(set(cpus)) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("use distinct authorized CPU IDs")
    locked_sources()

    def lane(index):
        for case_id in cases[index :: len(cpus)]:
            directory = None
            if detector == "ordinary-native" and fresh_root is not None and case_id in RAW_CASES:
                directory = fresh_root / case_id
                if not (directory / "raw-receipt.json").exists():
                    raise ValueError(
                        f"{case_id} has no successful receipt in the selected raw replay"
                    )
            predict(case_id, detector, work, cpus[index], directory)

    with ThreadPoolExecutor(max_workers=len(cpus)) as executor:
        list(executor.map(lane, range(len(cpus))))


def publish(work, output):
    source = {}
    for detector in DETECTORS:
        source[detector] = [
            json.loads((work / detector / f"{case}.json").read_bytes()) for case in TIMING_IDS
        ]
    for ordinary, capture in zip(*(source[k] for k in DETECTORS), strict=True):
        (offer,) = _complete_case(ordinary["id"])["regions"]
        for row in (ordinary, capture):
            if row.get("tile", offer) != offer:
                raise ValueError("position fit used a different assigned tile")
            row["tile"] = offer
        if (
            ordinary["id"] != capture["id"]
            or ordinary["capture_authority"] != capture["capture_authority"]
            or ordinary["catalog_sha256"] != capture["catalog_sha256"]
            or ordinary["track_config_sha256"] != capture["track_config_sha256"]
            or ordinary["implementation_sha256"] != capture["implementation_sha256"]
        ):
            raise ValueError("detector substitution changed capture, clock, catalogue or fitter")
        audit = capture["projection_audit"]
        if "same_lanes_and_timestamps" not in audit:
            raise ValueError("paired detector report lacks the capture-era projection audit")
        audit["status"] = "compared"
    files = {}
    for detector, filename in zip(DETECTORS, POSITION_FILES, strict=True):
        data = gzip.compress(b"".join(encoded(row) + b"\n" for row in source[detector]), mtime=0)
        write(output / filename, data)
        files[filename] = sha256(data).hexdigest()
    save_json(
        output / "prediction-lock.json", dict(files=files, cases=TIMING_IDS, **locked_sources())
    )


def score(output):
    """Open truth only after verifying the two published prediction receipts."""
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    paired = {}
    for detector, filename in zip(DETECTORS, POSITION_FILES, strict=True):
        path = _check(output / filename, lock["files"][filename])
        paired[detector] = read_predictions(path)
        if set(paired[detector]) != set(TIMING_IDS):
            raise ValueError("score needs the two complete timing cohorts")
    refs = {}
    for panel, prefix in (("ds26-common127", "DS26"), ("roof16", "DS29")):
        ids = [case for case in TIMING_IDS if case.startswith(prefix)]
        refs.update((r["id"], r) for r in references(panel, ids)[1])
    ordinary_v5 = read_predictions(ORDINARY_RECEIPT.parent / "positions.jsonl.gz")
    archived_robust = read_predictions(REPORT / "robust-em/positions.jsonl.gz")
    scored = []
    for case in TIMING_IDS:
        ref = refs[case]
        old_robust = archived_robust[case]["result"]
        fresh_capture = paired["capture-era"][case]["result"]
        native_v5 = ordinary_v5[case]["result"]
        for detector in DETECTORS:
            row = paired[detector][case]
            metrics = row["result"]["metrics"]
            for arm in ARMS:
                fitted = row["result"]["arms"][arm]
                previous, fresh = (r["arms"][arm] for r in (old_robust, fresh_capture))
                scored.append(
                    dict(
                        id=case,
                        detector=detector,
                        scope=row["variant"],
                        arm=arm,
                        status=row["result"]["status"],
                        error_km=distance_km(fitted["latlon"], ref["truth"]),
                        forced_error_km=distance_km(fitted.get("forced_latlon"), ref["truth"]),
                        conditional_rms_hz=fitted.get("rf_rms_hz"),
                        frequency_score=fitted.get("frequency_score"),
                        capture_era_v5_error_km=ref["reference"]["baseline"][arm]["error_km"],
                        ordinary_v5_error_km=distance_km(
                            native_v5["arms"][arm]["latlon"], ref["truth"]
                        ),
                        capture_port_position_shift_km=distance_km(
                            fresh.get("forced_latlon", fresh["latlon"]),
                            previous.get("forced_latlon", previous["latlon"]),
                        ),
                        capture_port_same_decision=fresh_capture["status"] == old_robust["status"],
                        tracks=metrics["tracks"],
                        raw_wall_s=row["acquisition"].get("raw_wall_s"),
                        tracking_wall_s=metrics["tracker"]["wall_s"],
                        tracking_cpu_s=metrics["tracker"]["cpu_s"],
                        fit_wall_s=metrics["fit_wall_s"],
                        fit_cpu_s=metrics["fit_cpu_s"],
                        tracker_peak_rss_kib=metrics["track_peak_rss_kib"],
                        fit_peak_rss_kib=metrics["fit_peak_rss_kib"],
                    )
                )
    csv_file(output / "scores.csv", scored)
    summary = {
        detector: {
            arm: distribution(
                r["error_km"] for r in scored if r["detector"] == detector and r["arm"] == arm
            )
            for arm in ARMS
        }
        for detector in DETECTORS
    }
    save_json(output / "summary.json", summary)


def assemble_raw(directory, case_id, deadline_s, detector):
    """Only seal complete native factors, leaving graph and position to another stage."""
    exits = json.loads((directory / "raw-worker-exits.json").read_bytes())["exit_codes"]
    if exits != [0, 0]:
        raise ValueError(
            f"whole IQ replay exited before both authenticated lanes completed: {exits}"
        )
    case = _load_case(case_id)
    capture = json.loads((directory / "capture.json").read_bytes())
    lanes = []
    for lane in range(2):
        with (directory / f"replayed-{lane}.jsonl").open() as stream:
            lanes.append(list(map(json.loads, stream)))
    document, metrics = recording_to_v5.native_document(case, lanes, capture, detector)
    path = directory / "native.json"
    recording_to_v5.save(path, document)
    started = float((directory / "started_unix_s").read_text())
    wall = time.time() - started
    if wall > deadline_s:
        raise TimeoutError("complete raw assembly exceeded the physical replay budget")
    receipt = dict(
        id=case_id,
        native_sha256=_sha(path),
        detector_sha256=document["provenance"]["detector_sha256"],
        native_input_manifest_sha256=document["source"]["input_manifest_sha256"],
        analysis_manifest_sha256=document["source"]["analysis_manifest_sha256"],
        raw_gate="fresh whole-recording native GLRT",
        raw_wall_s=wall,
        **metrics,
    )
    recording_to_v5.save(directory / "raw-receipt.json", receipt)
    print(case_id, round(wall, 2), receipt["native_sha256"], flush=True)
    return receipt


def fresh(case_id, output, cpus, native_library=NATIVE_LIBRARY):
    return recording_to_v5.run_recording(
        case_id,
        local_output(output) / case_id,
        cpus,
        RAW_DEADLINE_S,
        native_library,
        finish=assemble_raw,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--fresh", type=Path)
    action.add_argument("--detector", choices=DETECTORS)
    action.add_argument("--publish", type=Path)
    action.add_argument("--score", type=Path)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--fresh-root", type=Path)
    parser.add_argument("--cases", nargs="+", choices=TIMING_IDS)
    parser.add_argument("--cpus", type=int, nargs=2, default=(10, 11))
    args = parser.parse_args()
    cases = args.cases or (RAW_CASES if args.fresh is not None else TIMING_IDS)
    if len(cases) != len(set(cases)):
        parser.error("run each whole recording once")
    if args.score is not None:
        score(local_output(args.score))
    elif args.fresh is not None:
        if not set(cases) <= set(RAW_CASES):
            parser.error("fresh raw replay is limited to the two smoke recordings")
        for case_id in cases:
            fresh(case_id, args.fresh, args.cpus)
    elif args.work is None:
        parser.error("position replay and publication require a workspace")
    elif args.publish is not None:
        publish(local_output(args.work), local_output(args.publish))
    else:
        replay_batch(local_output(args.work), args.cpus, args.detector, cases, args.fresh_root)


if __name__ == "__main__":
    main()
