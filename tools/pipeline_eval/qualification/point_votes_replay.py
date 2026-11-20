"""Run and seal the anonymous GLRT point-pair receiver on frozen IQ-independent inputs."""

import argparse
import gzip
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time

from ..__main__ import encoded, read_predictions, save_json, write
from ..scoring import distance_km, score, validate_result
from ..variants import point_votes
from .cold_input import load, matched_offers
from .full_v5_check import _load_case

TIMING_IDS = ("DS26-0036", "DS26-0122", "DS26-0237", "DS29-0082", "DS29-0174", "DS29-0247")
MODES = ("global", "matched-tile")


def _predict(case_id, mode, cpu):
    os.sched_setaffinity(0, {cpu})
    start, cpu_start = perf_counter(), process_time()
    input_hash = None
    native_hash = None
    catalog_hash = None
    try:
        capture = load(case_id)
        tile = matched_offers(case_id)[0]["center"] if mode == "matched-tile" else None
        native_hash, catalog_hash = capture.native_sha256, capture.catalog_sha256
        input_hash = sha256(encoded((native_hash, catalog_hash, tile))).hexdigest()
        result = point_votes.solve(capture, tile=tile)
    except (OSError, ValueError) as exc:
        result = dict(status="failed", boundary=point_votes.BOUNDARY, reason=str(exc), metrics={})
    validate_result(result)
    return dict(
        id=case_id,
        method="point_votes",
        mode=mode,
        cpu=cpu,
        input_sha256=input_hash,
        native_sha256=native_hash,
        catalog_sha256=catalog_hash,
        implementation_sha256=sha256(Path(point_votes.__file__).read_bytes()).hexdigest(),
        worker_wall_s=perf_counter() - start,
        worker_cpu_s=process_time() - cpu_start,
        result=result,
    )


def _write_predictions(output, cases, records):
    locks = {}
    for mode in MODES:
        raw = b"".join(encoded(records[case, mode]) + b"\n" for case in cases)
        compressed = gzip.compress(raw, mtime=0)
        name = f"{mode}.jsonl.gz"
        write(output / name, compressed)
        locks[name] = sha256(compressed).hexdigest()
    save_json(output / "prediction-lock.json", dict(cases=cases, files=locks))


def _read_locked(output):
    lock = json.loads((output / "prediction-lock.json").read_bytes())
    predictions = {}
    for mode in MODES:
        path = output / f"{mode}.jsonl.gz"
        if sha256(path.read_bytes()).hexdigest() != lock["files"][path.name]:
            raise ValueError("position submission changed after sealing")
        lines = read_predictions(path)
        if set(lines) != set(lock["cases"]) or any(row["mode"] != mode for row in lines.values()):
            raise ValueError("position submission changed its attempted cohort or policy mode")
        predictions[mode] = lines
    return lock["cases"], predictions


def bind_sources(output):
    """Bind source digests and replay the corrected gate on saved finalists before scoring."""
    if (output / "scores.json").exists():
        raise ValueError("existing scores disallow rewriting predictions")
    cases, predictions = _read_locked(output)
    records = {}
    implementation = sha256(Path(point_votes.__file__).read_bytes()).hexdigest()
    for mode, lines in predictions.items():
        for case_id, row in lines.items():
            item = _load_case(case_id)
            native, catalog = item["native"]["sha256"], item["catalog"]["sha256"]
            tile = matched_offers(case_id)[0]["center"] if mode == "matched-tile" else None
            expected = sha256(encoded((native, catalog, tile))).hexdigest()
            if row["input_sha256"] not in (None, expected):
                raise ValueError("prediction composite digest does not bind the frozen inputs")
            row["native_sha256"] = native if row["input_sha256"] is not None else None
            row["catalog_sha256"] = catalog if row["input_sha256"] is not None else None
            result = row["result"]
            metrics = result["metrics"]
            if "spatially_separated_finalists" not in metrics and "finalist_locations" in metrics:
                metrics.update(
                    point_votes.validation_metrics(
                        metrics["finalist_locations"],
                        metrics["finalist_validation"],
                        supplied=mode == "matched-tile",
                    )
                )
                passed, reason = point_votes.decision(metrics)
                result.update(status="ok" if passed else "withheld", reason=reason)
                for arm in result["arms"].values():
                    arm["latlon"] = arm["forced_latlon"] if passed else None
                row.update(
                    measured_implementation_sha256=row["implementation_sha256"],
                    implementation_sha256=implementation,
                    decision_gate_recomputed=True,
                )
            validate_result(result)
            records[case_id, mode] = row
    _write_predictions(output, cases, records)


def score_sealed(output):
    cases, predictions = _read_locked(output)

    from ..corpus import _references, _selection

    _, files = _selection("smoke")
    references = list(_references(cases, files))
    document = {}
    for mode, lines in predictions.items():
        summary, rows = score(references, lines)
        for row in rows:
            ref = next(item for item in references if item["id"] == row["id"])
            center = matched_offers(row["id"])[0]["center"]
            row["supplied_tile_center_error_km"] = distance_km(center, ref["truth"])
        document[mode] = dict(summary=summary, cases=rows)
    save_json(output / "scores.json", document)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--cases", nargs="+", choices=TIMING_IDS, default=TIMING_IDS)
    p.add_argument("--cpus", nargs="+", type=int, default=(8, 9, 10, 11))
    p.add_argument("--score-sealed", action="store_true")
    args = p.parse_args()
    if args.score_sealed:
        score_sealed(args.out)
        return
    if len(set(args.cases)) != len(args.cases):
        p.error("each recording requires a single attempt per mode")
    if not set(args.cpus) <= os.sched_getaffinity(0) or len(set(args.cpus)) != len(args.cpus):
        p.error("supply distinct permitted CPUs")
    records = {}
    with ProcessPoolExecutor(max_workers=len(args.cpus)) as pool:
        jobs = [(case, mode) for case in args.cases for mode in MODES]
        for begin in range(0, len(jobs), len(args.cpus)):
            pending = [
                pool.submit(_predict, case, mode, cpu)
                for (case, mode), cpu in zip(
                    jobs[begin : begin + len(args.cpus)],
                    args.cpus,
                    strict=False,
                )
            ]
            for job in as_completed(pending):
                record = job.result()
                case_id, mode = record["id"], record["mode"]
                records[case_id, mode] = record
                print(
                    case_id,
                    mode,
                    record["result"]["status"],
                    round(record["worker_wall_s"], 2),
                    flush=True,
                )
    _write_predictions(args.out, args.cases, records)


if __name__ == "__main__":
    main()
