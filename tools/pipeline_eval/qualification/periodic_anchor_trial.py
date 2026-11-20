"""Authenticate the complete factor mix and run paired compact cavity positions."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from time import perf_counter

from ..__main__ import encoded, local_output, read_predictions, references, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import orbit_projector, periodic_anchor, v5_core, v5_lean
from ..variants.iq_stream import MIB, _chunk_member, _read_prefix
from .full_v5_check import BULK, REPO, _load_case, _sha
from .prefix_figures import TIMING_IDS, csv_file
from .raw_robust import ORDINARY_RECEIPT, prior_directory
from .recording_to_v5 import bind_request, digest, native_document, save

METHOD = "periodic_anchor"
CANDIDATE = "periodic-reference-64"
ORDINARY = periodic_anchor.ORDINARY_CONTROL
CAPTURE_ERA = periodic_anchor.REFERENCE_CONTROL
SOURCE_CONTROL = REPO / "reports/2026_11_19_short_receiver/search-budget"
MAX_POSE_S = 600
FILES = {
    CANDIDATE: "positions.jsonl.gz",
    ORDINARY: "ordinary-control-positions.jsonl.gz",
    CAPTURE_ERA: "capture-era-control-positions.jsonl.gz",
}


def verified_bytes(path, sha, length):
    data = _read_prefix(path, length + 1)
    if len(data) > length or sha256(data).hexdigest() != sha:
        raise ValueError("scheduled input failed its bounded SHA-256 check")
    return data


def read_schedule(case):
    """Read all hash-bound target, sweep and acquisition index rows without IQ decode."""
    result = []
    for number, locator in enumerate(case["recording"]["segments"]):
        path = BULK / locator["path"]
        manifest = json.loads(verified_bytes(path, locator["sha256"], 64 * 1024))
        if (
            manifest["schema_version"],
            manifest["sample_rate_hz"],
            manifest["window_ms"],
            manifest["receiver_ids"],
            manifest["sample_format"],
            manifest["sample_layout"],
            manifest["status"],
        ) != (2, 10_000_000, 20, [0, 1], "ci16_le", "sample_receiver_iq", "complete"):
            raise ValueError("schedule requires sealed dual-CI16 at original rate and geometry")
        targets = {row["target_id"]: row for row in manifest["configuration"]["targets"]}
        sequence = 0
        for chunk in manifest["chunks"]:
            if chunk["index_bytes"] > MIB or chunk["first_sequence"] != sequence:
                raise ValueError("schedule index is oversized or misses a visit")
            index = _chunk_member(path.parent, chunk["index_relative_path"])
            raw = verified_bytes(
                index, chunk["index_sha256"].removeprefix("sha256:"), chunk["index_bytes"]
            )
            lines = raw.splitlines()
            if len(raw) != chunk["index_bytes"] or len(lines) != chunk["window_count"]:
                raise ValueError("scheduled visit index size differs from its manifest")
            for entry in map(json.loads, lines):
                target = targets[entry["target_id"]]
                acq = entry["acquisition"]
                if entry["sequence"] != sequence or entry["receiver_count"] != 2:
                    raise ValueError("signed schedule geometry or visit order changed")
                result.append(
                    dict(
                        segment=number,
                        sequence=sequence,
                        visit=acq["global_visit"],
                        sweep=acq["sweep"],
                        target_index=acq["target_index"],
                        channel=target["channel"],
                        edge=target["edge"],
                        iq_sha256=entry["iq_sha256"],
                        sample_start=acq["sample_start"],
                        sample_end=acq["sample_end"],
                        payload_bytes=entry["payload_bytes"],
                    )
                )
                sequence += 1
        if sequence != manifest["window_count"]:
            raise ValueError("segment schedule is incomplete")
    if len(result) != case["recording"]["window_count"]:
        raise ValueError("physical recording schedule is incomplete")
    return result


def read_archives(case):
    case_id = case["id"]
    expected = json.loads(ORDINARY_RECEIPT.read_bytes())["recordings"][case_id]
    directory = prior_directory(case_id)
    paths = {ORDINARY: directory / "native.json", CAPTURE_ERA: BULK / case["native"]["path"]}
    hashes = {ORDINARY: expected["native_sha256"], CAPTURE_ERA: case["native"]["sha256"]}
    documents = {}
    for key, path in paths.items():
        data = path.read_bytes()
        if sha256(data).hexdigest() != hashes[key]:
            raise ValueError("complete detector factor archive differs from its published digest")
        documents[key] = json.loads(data)
    lanes = []
    for lane in range(2):
        with (directory / f"replayed-{lane}.jsonl").open() as stream:
            lanes.append(list(map(json.loads, stream)))
    receipt = directory / "capture.json"
    capture = json.loads(receipt.read_bytes()) if receipt.is_file() else None
    reconstructed, metrics = native_document(case, lanes, capture)
    source = reconstructed["source"]
    if (
        reconstructed != documents[ORDINARY]
        or source["analysis_manifest_sha256"] != expected["analysis_manifest_sha256"]
        or source["input_manifest_sha256"] != expected["input_manifest_sha256"]
        or reconstructed["provenance"]["detector_sha256"] != expected["detector_sha256"]
    ):
        raise ValueError("whole ordinary lane receipts fail to reproduce the source")
    visits = sorted(
        (row for lane in lanes for row in lane if row["kind"] == "visit"), key=lambda r: r["visit"]
    )
    return paths, hashes, documents, visits, metrics


def prepare(case_id, work):
    start = perf_counter()
    case = _load_case(case_id)
    directory = work / case_id
    directory.mkdir(parents=True, exist_ok=False)
    schedule = read_schedule(case)
    paths, hashes, docs, visits, ordinary_metrics = read_archives(case)
    for scheduled, actual in zip(schedule, visits, strict=True):
        if scheduled["payload_bytes"] != actual["input_bytes"] or any(
            scheduled[key] != actual[key]
            for key in ("segment", "sequence", "visit", "iq_sha256", "sample_start", "sample_end")
        ):
            raise ValueError("recorded target schedule differs from whole replay visit")
    probes, evidence = periodic_anchor.mix(docs[ORDINARY], docs[CAPTURE_ERA], schedule)
    analysis = digest([CANDIDATE, hashes, evidence["selected_visits"], probes])
    ordinary = docs[ORDINARY]
    document = dict(
        ordinary,
        source=dict(ordinary["source"], probes=probes, analysis_manifest_sha256=analysis),
        provenance=dict(
            ordinary["provenance"],
            run_id="replay-" + analysis[7:39],
            scope="ordinary native with periodic capture-era sweeps",
        ),
    )
    periodic = directory / "native.json"
    save(periodic, document)
    paths[CANDIDATE] = periodic
    hashes[CANDIDATE] = _sha(periodic)
    proof = dict(
        id=case_id,
        factor_sha256=hashes,
        paths={key: str(path) for key, path in paths.items()},
        scheduled_visits=len(schedule),
        schedule_sha256=digest(schedule),
        first_sweep=[schedule[i] for i in evidence["selected_visits"][:8]],
        verified_ordinary_detector_cpu_s=ordinary_metrics["detector_cpu_s"],
        scheduled_valid_visits=ordinary_metrics["processed_windows"],
        preparation_wall_s=perf_counter() - start,
        **evidence,
    )
    save(directory / "schedule.json", proof)
    print(case_id, len(evidence["selected_sweeps"]), evidence["selected_valid_visits"], flush=True)


def solver_sources():
    paths = [
        orbit_projector.KERNEL,
        *(Path(m.__file__) for m in (orbit_projector, v5_core, v5_lean)),
    ]
    return {path.name: _sha(path) for path in paths}


def fit(case_id, variant, cpu, work):
    os.sched_setaffinity(0, {cpu})
    case = _load_case(case_id)
    schedule = json.loads((work / case_id / "schedule.json").read_bytes())
    folder = work / case_id / variant
    folder.mkdir(exist_ok=False)
    path = Path(schedule["paths"][variant])
    if _sha(path) != schedule["factor_sha256"][variant]:
        raise ValueError("position input changed after schedule composition")
    bound = bind_request(case, path, folder / "request.json")
    (folder / "position").mkdir()
    started = perf_counter()
    before = getrusage(RUSAGE_CHILDREN)
    v5_lean.TIMEOUT_S = MAX_POSE_S - 5
    result = orbit_projector.run(bound, folder / "position")
    after = getrusage(RUSAGE_CHILDREN)
    elapsed = perf_counter() - started
    result["metrics"]["position_attempted"] = True
    validate_result(result)
    row = dict(
        id=case_id,
        method=METHOD,
        variant=variant,
        mode="matched-tile",
        cpu=cpu,
        native_sha256=schedule["factor_sha256"][variant],
        input_sha256=bound["native_sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        factor_sha256=schedule["factor_sha256"],
        schedule_sha256=schedule["schedule_sha256"],
        solver_sha256=digest(solver_sources()),
        request_sha256=_sha(folder / "position/request.json"),
        worker_wall_s=elapsed,
        worker_cpu_s=(after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime),
        result=result,
    )
    save(folder / "receipt.json", row)
    print(case_id, variant, result["status"], round(elapsed, 2), flush=True)
    return row


def run(case, work_dir):
    """Run the preset anchor receiver on one of the six fully bound captures."""
    case_id = case.get("id")
    affinity = os.sched_getaffinity(0)
    try:
        if case_id not in TIMING_IDS:
            raise ValueError("no authenticated dual-detector schedule for this recording")
        work = local_output(work_dir)
        prepare(case_id, work)
        row = fit(case_id, CANDIDATE, min(affinity), work)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return dict(
            status="unavailable",
            reason=str(error),
            boundary=orbit_projector.BOUNDARY,
            metrics={},
            arms={arm: {"latlon": None} for arm in ARMS},
        )
    finally:
        os.sched_setaffinity(0, affinity)
    return dict(
        row["result"],
        input_binding={
            key: row[key]
            for key in (
                "input_sha256",
                "native_sha256",
                "catalog_sha256",
                "factor_sha256",
                "schedule_sha256",
                "solver_sha256",
                "request_sha256",
            )
        },
    )


def fit_batch(cases, cpus, work, variants):
    if len(cpus) != len(set(cpus)) or not set(cpus) <= {0, 1, 2, 3} & os.sched_getaffinity(0):
        raise ValueError("fits use distinct available CPUs 0–3")
    jobs = [(case_id, variant) for case_id in cases for variant in variants]
    with ProcessPoolExecutor(max_workers=len(cpus)) as executor:
        for i in range(0, len(jobs), len(cpus)):
            batch = jobs[i : i + len(cpus)]
            active = [
                executor.submit(fit, case, variant, cpu, work)
                for (case, variant), cpu in zip(batch, cpus, strict=False)
            ]
            for future in as_completed(active):
                future.result()


def capture_controls():
    receipt = json.loads((SOURCE_CONTROL / "receipt.json").read_bytes())
    if receipt["scientific_source"] != v5_lean.SOURCE_SHA256 or any(
        receipt["source"][name] != value for name, value in solver_sources().items()
    ):
        raise ValueError("capture-era controls used a different compact cavity implementation")
    path = SOURCE_CONTROL / "orbit_projector.jsonl.gz"
    if _sha(path) != receipt["files"][path.name]:
        raise ValueError("published compact capture-era controls changed")
    return read_predictions(path)


def publish(work, output):
    rows = {key: [] for key in FILES}
    control = capture_controls()
    schedules = {}
    for case_id in TIMING_IDS:
        case = _load_case(case_id)
        schedule = json.loads((work / case_id / "schedule.json").read_bytes())
        schedules[case_id] = {k: v for k, v in schedule.items() if k != "paths"}
        for variant in (CANDIDATE, ORDINARY):
            row = json.loads((work / case_id / variant / "receipt.json").read_bytes())
            if (
                row["id"] != case_id
                or row["variant"] != variant
                or row["native_sha256"] != schedule["factor_sha256"][variant]
                or row["catalog_sha256"] != case["catalog"]["sha256"]
                or row["solver_sha256"] != digest(solver_sources())
            ):
                raise ValueError("position receipt differs from the certified schedule or solver")
            rows[variant].append(row)
        original = control[case_id]
        if (
            original["native_sha256"] != schedule["factor_sha256"][CAPTURE_ERA]
            or original["catalog_sha256"] != case["catalog"]["sha256"]
        ):
            raise ValueError(
                "capture-era compact endpoint differs from the original interference arm"
            )
        rows[CAPTURE_ERA].append(
            dict(
                original,
                method=METHOD,
                variant=CAPTURE_ERA,
                mode="matched-tile",
                factor_sha256=schedule["factor_sha256"],
                schedule_sha256=schedule["schedule_sha256"],
                solver_sha256=digest(solver_sources()),
            )
        )
    files = {}
    for variant, name in FILES.items():
        data = gzip.compress(b"".join(encoded(row) + b"\n" for row in rows[variant]), mtime=0)
        write(output / name, data)
        files[name] = sha256(data).hexdigest()
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=TIMING_IDS,
            files=files,
            solver_sources=solver_sources(),
            schedule=periodic_anchor.PERIOD,
        ),
    )
    save_json(output / "schedule-receipts.json", schedules)


def score(output):
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    if tuple(lock["cases"]) != tuple(TIMING_IDS):
        raise ValueError("expected both calibration arms for the fixed timing cohort")
    records = {}
    for variant, name in FILES.items():
        path = output / name
        if _sha(path) != lock["files"][name]:
            raise ValueError("numeric predictions changed after the seal")
        records[variant] = read_predictions(path)
    refs = {}
    for panel, prefix in (("ds26-common127", "DS26"), ("roof16", "DS29")):
        selected = [i for i in TIMING_IDS if i.startswith(prefix)]
        refs.update((r["id"], r) for r in references(panel, selected)[1])
    rows = []
    for case in TIMING_IDS:
        for variant in FILES:
            record = records[variant][case]
            result = record["result"]
            for arm in ARMS:
                outcome = result["arms"][arm]
                rows.append(
                    dict(
                        id=case,
                        variant=variant,
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(outcome["latlon"], refs[case]["truth"]),
                        conditional_rms_hz=outcome.get("rf_rms_hz"),
                        archived_final_v5_error_km=refs[case]["reference"]["baseline"][arm][
                            "error_km"
                        ],
                        worker_wall_s=record["worker_wall_s"],
                        worker_cpu_s=record.get("worker_cpu_s"),
                    )
                )
    csv_file(output / "scores.csv", rows)
    save_json(
        output / "summary.json",
        {
            variant: {
                arm: distribution(
                    r["error_km"] for r in rows if r["variant"] == variant and r["arm"] == arm
                )
                for arm in ARMS
            }
            for variant in FILES
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--fit", action="store_true")
    action.add_argument("--publish", type=Path)
    action.add_argument("--score", type=Path)
    parser.add_argument("--cases", nargs="+", default=TIMING_IDS, choices=TIMING_IDS)
    parser.add_argument("--cpus", nargs="+", type=int, default=(0, 1, 2, 3))
    parser.add_argument(
        "--variants", nargs="+", default=(CANDIDATE, ORDINARY), choices=(CANDIDATE, ORDINARY)
    )
    args = parser.parse_args()
    if args.score is not None:
        return score(local_output(args.score))
    if args.work is None:
        parser.error("preparation, replay and publication require a working directory")
    work = local_output(args.work)
    if args.prepare:
        for case in args.cases:
            prepare(case, work)
    elif args.fit:
        fit_batch(args.cases, args.cpus, work, args.variants)
    else:
        publish(work, local_output(args.publish))


if __name__ == "__main__":
    main()
