"""Replay the compact projector on the frozen 135-recording roof panel."""

import argparse
import fcntl
import gzip
import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import SimpleQueue

from .. import corpus
from ..__main__ import (
    DEFAULT_OUT,
    ROOT,
    encoded,
    local_output,
    public_cases,
    read_predictions,
    references,
    run_one,
    write,
)
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from ..variants import orbit_projector
from .prefix_figures import REPORT as CHECKPOINTS
from .prefix_figures import TIMING_IDS, cohorts, csv_file, load_rows

METHOD = "orbit_projector"
REPORT = ROOT / "reports/2026_11_19_receiver_duty"
SCRATCH = Path("/srv/bulk/leo-dev/receiver-duty-20261119")
STRESS = "DS26-0066"
SOURCES = {**dict.fromkeys(TIMING_IDS, "paired_timing"), STRESS: "stress"}
COMPARATORS = ("cavity", *ROLES)
PREDICTIONS = "projector-roof.jsonl.gz"
ARCHIVE_RECEIPT = "projector-roof-receipt.json"
TIMING_RECEIPT = "projector-pairs.jsonl.gz"
STRESS_RECEIPT = "stress.jsonl.gz"
SHA256 = re.compile(r"[0-9a-f]{64}")


def roster():
    ds26 = references("ds26-common127", None)[1]
    ds29 = [r for r in references("roof16", None)[1] if r["group"] == "DS29"]
    refs = ds26 + ds29
    if (
        len(ds26) != 127
        or any(r["group"] != "DS26" for r in ds26)
        or len(ds29) != 8
        or len({r["id"] for r in refs}) != 135
    ):
        raise ValueError("expected 127 unique DS26 and eight unique DS29 recordings")
    return refs


def source_hashes():
    return tuple(
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(orbit_projector.__file__), orbit_projector.KERNEL)
    )


def input_hash(case):
    return hashlib.sha256(encoded(case)).hexdigest()


def prediction_hashes(record):
    return record.get("implementation_sha256"), record["result"]["metrics"].get("kernel_sha256")


def validate_prediction(record, hashes, *, case=None, allow_failure=False):
    ident = record["id"]
    digest = record.get("input_sha256", "")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError(f"{ident} prediction has an invalid input digest")
    if case is not None and (ident != case["id"] or digest != input_hash(case)):
        raise ValueError(f"{case['id']} prediction input differs from the frozen request")
    result = record["result"]
    validate_result(result)
    incomplete = allow_failure and result["status"] != "ok"
    if record.get("method", METHOD) != METHOD or any(
        actual != expected and (not incomplete or actual is not None)
        for actual, expected in zip(prediction_hashes(record), hashes, strict=True)
    ):
        raise ValueError(f"{ident} implementation or kernel provenance differs")
    if not allow_failure and result["status"] != "ok":
        raise ValueError(f"{ident} reused prediction did not complete successfully")
    if result["status"] == "ok" and (
        result["boundary"] != orbit_projector.BOUNDARY or "arms" not in result
    ):
        raise ValueError(f"{ident} did not report the native paired cavity boundary")
    return record


def validate_confirmation(record, hashes, *, case=None):
    if record.get("source") != "confirmation" or tuple(record.get("expected_sha256", ())) != hashes:
        raise ValueError(f"{record['id']} confirmation provenance differs from the current study")
    if prior := record.get("prior_attempt"):
        if (
            prior["result"]["status"] not in ("failed", "timed_out")
            or "prior_attempt" in prior
            or any(prior[k] != record[k] for k in ("id", "input_sha256"))
        ):
            raise ValueError(f"{record['id']} retry requires one recorded worker failure")
        validate_confirmation(prior, hashes, case=case)
    return validate_prediction(record, hashes, case=case, allow_failure=True)


def ordered_predictions(refs, records):
    expected = {r["id"] for r in refs}
    if (
        len(expected) != len(refs)
        or records.keys() != expected
        or any(ident != record["id"] for ident, record in records.items())
    ):
        raise ValueError("predictions must cover the frozen recording roster exactly")
    return [records[r["id"]] for r in refs]


def historical_predictions(receipts, previous=None):
    timing_file = receipts / TIMING_RECEIPT
    stress_file = receipts / STRESS_RECEIPT
    if previous is not None:
        raw_pairs = previous / "projector-pairs"
        timing_file = raw_pairs / "paired.jsonl.gz"
        (stress_file,) = previous.glob(
            f"geometry/ds26-common127/{METHOD}/subset-*/current/predictions.jsonl"
        )
    with gzip.open(timing_file, "rt") as stream:
        rows = list(map(json.loads, stream))
    finished = {(r["id"], r["method"]): r for r in rows}
    expected = {(ident, method) for ident in TIMING_IDS for method in (METHOD, "v5_lean")}
    if (
        len(rows) != len(expected)
        or set(finished) != expected
        or any(r["result"]["status"] != "ok" for r in rows)
    ):
        raise ValueError("the six full-channel projector timing pairs must finish first")
    stress = read_predictions(stress_file)
    if set(stress) != {STRESS}:
        raise ValueError("expected the single predeclared stress prediction")
    reused = {STRESS: stress[STRESS]}
    for ident in TIMING_IDS:
        record = finished[ident, METHOD]
        if previous is not None:
            individual = json.loads((raw_pairs / f"{ident}-{METHOD}.json").read_bytes())
            if individual != record:
                raise ValueError(f"{ident} timing prediction differs from its completed receipt")
        if record["input_sha256"] != finished[ident, "v5_lean"]["input_sha256"]:
            raise ValueError(f"{ident} timing prediction differs from the completed input pair")
        reused[ident] = record
    historical_hashes = prediction_hashes(reused[STRESS])
    if any(
        not isinstance(value, str) or not SHA256.fullmatch(value) for value in historical_hashes
    ):
        raise ValueError("invalid implementation or kernel provenance for historical predictions")
    records = {
        ident: dict(
            validate_prediction(record, historical_hashes),
            source=SOURCES[ident],
        )
        for ident, record in reused.items()
    }
    return records, historical_hashes


def reuse(receipts, hashes, *, cases=None, previous=None, archive=None, rerun_stale=False):
    if archive is None:
        seal = receipts / ARCHIVE_RECEIPT
        archive = read_archive_receipt(seal if seal.is_file() else REPORT / ARCHIVE_RECEIPT)
    actual = file_digests(receipts / name for name in (TIMING_RECEIPT, STRESS_RECEIPT))
    check_digests(actual, {name: archive["files"].get(name) for name in actual})
    records, historical_hashes = historical_predictions(receipts)
    if previous is not None and historical_predictions(receipts, previous) != (
        records,
        historical_hashes,
    ):
        raise ValueError("shipped timing and stress receipts differ from the original runs")
    if historical_hashes != hashes:
        if rerun_stale:
            return {}
        raise ValueError("historical implementation or kernel provenance differs")
    if cases is not None:
        for ident, record in records.items():
            validate_prediction(record, hashes, case=cases[ident])
    return records


def load_cases(refs, cache):
    ds26 = [r for r in refs if r["group"] == "DS26"]
    ds29 = [r for r in refs if r["group"] == "DS29"]
    return {
        case["id"]: case
        for panel, selected in (("ds26-common127", ds26), ("roof16", ds29))
        for case in public_cases(panel, selected, cache)
    }


def run_panel(refs, work, receipts, cache, cpus, timeout, *, previous=None, retry=False):
    cpus = tuple(cpus)
    if not cpus or len(set(cpus)) != len(cpus) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("pass distinct permitted CPUs for the concurrent projector workers")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=True)
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        hashes = source_hashes()
        cases = load_cases(refs, cache)
        records = reuse(receipts, hashes, cases=cases, previous=previous, rerun_stale=True)
        if not records:
            # Leave the original confirmation journal with the version that produced it.
            work = work / "versions" / hashlib.sha256(encoded(hashes)).hexdigest()
            work.mkdir(parents=True, exist_ok=True)
        journal = work / "predictions"
        journal.mkdir(exist_ok=True)
        for path in sorted(journal.glob("*.json")):
            ident = path.stem
            if ident not in cases or ident in records:
                raise ValueError(f"unexpected completed prediction {ident}")
            record = json.loads(path.read_bytes())
            records[ident] = validate_confirmation(record, hashes, case=cases[ident])

        available = SimpleQueue()
        for cpu in cpus:
            available.put(cpu)

        def measure(ident):
            cpu = available.get()
            try:
                record = run_one(METHOD, cases[ident], work, timeout, cpu)
                if ident in retries:
                    record["prior_attempt"] = retries[ident]
                record.update(source="confirmation", expected_sha256=hashes, method=METHOD, cpu=cpu)
                validate_confirmation(record, hashes, case=cases[ident])
                write(journal / f"{ident}.json", encoded(record) + b"\n")
                return record
            finally:
                available.put(cpu)

        retries = {
            ident: record
            for ident, record in records.items()
            if retry
            and record["result"]["status"] in ("failed", "timed_out")
            and "prior_attempt" not in record
        }
        remaining = [r["id"] for r in refs if r["id"] not in records or r["id"] in retries]
        print(
            f"Verified {len(records)} saved predictions. Starting {len(remaining)} recordings.",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
            futures = [pool.submit(measure, ident) for ident in remaining]
            for future in as_completed(futures):
                record = future.result()
                records[record["id"]] = record
                print(
                    len(records),
                    len(refs),
                    record["id"],
                    record["result"]["status"],
                    round(record["worker_wall_s"], 2),
                    flush=True,
                )
        if source_hashes() != hashes:
            raise ValueError("projector source changed during the confirmation")
        return records, hashes


def meters(point, reference):
    value = distance_km(point, reference)
    return None if value is None else value * 1000


def comparison_rows(refs, records, checkpoints):
    ordered = ordered_predictions(refs, records)
    if checkpoints.keys() != records.keys():
        raise ValueError("archived cavity checkpoints must cover the frozen recording roster")
    rows = []
    for ref, record in zip(refs, ordered, strict=True):
        result = record["result"]
        archived = checkpoints[ref["id"]][2]["stages"]
        for arm in ARMS:
            prediction = result.get("arms", {}).get(arm, {})
            point = prediction.get("latlon")
            cavity = archived["cavity"][arm]
            status = result["status"]
            if status == "ok" and point is None:
                status = "withheld"
            row = dict(
                recording=ref["id"],
                dataset=ref["group"],
                arm=arm,
                source=record["source"],
                status=status,
                reason=result.get("reason"),
                projector_latitude_deg=None if point is None else point[0],
                projector_longitude_deg=None if point is None else point[1],
                orbit_projector_error_km=distance_km(point, ref["truth"]),
                orbit_projector_conditional_rms_hz=prediction.get("rf_rms_hz"),
                cavity_error_km=distance_km(cavity["latlon"], ref["truth"]),
                cavity_conditional_rms_hz=cavity["conditional_rms_hz"],
                cavity_coordinate_delta_m=meters(point, cavity["latlon"]),
                baseline_conditional_rms_hz=archived["final"][arm]["conditional_rms_hz"],
            )
            for role in ROLES:
                reference = ref["reference"][role][arm]
                row[f"{role}_error_km"] = distance_km(reference["latlon"], ref["truth"])
                row[f"{role}_original_report_rms_hz"] = reference["rf_rms_hz"]
                row[f"{role}_coordinate_delta_m"] = meters(point, reference["latlon"])
            rows.append(row)
    return rows


def distribution_rows(rows):
    summaries = []
    for dataset in ("DS26", "DS29", "all"):
        for arm in ARMS:
            group = [r for r in rows if r["arm"] == arm and dataset in (r["dataset"], "all")]
            if not group:
                continue
            methods = {}
            for method in (METHOD, *COMPARATORS):
                errors = [r[f"{method}_error_km"] for r in group]
                stats = distribution(errors)
                conditional_rms = distribution(r.get(f"{method}_conditional_rms_hz") for r in group)
                original_rms = distribution(
                    r.get(f"{method}_original_report_rms_hz") for r in group
                )
                # The projector row measures the same-boundary discrepancy to the archived cavity.
                comparator = "cavity" if method == METHOD else method
                deltas = distribution(r[f"{comparator}_coordinate_delta_m"] for r in group)
                methods[method] = dict(
                    dataset=dataset,
                    arm=arm,
                    method=method,
                    scheduled=len(group),
                    published=stats["n"],
                    coverage=stats["n"] / len(group),
                    median_error_km=stats["p50"],
                    p95_error_km=stats["p95"],
                    worst_error_km=stats["max"],
                    within_5_km=sum(e is not None and e <= 5 for e in errors),
                    median_conditional_rms_hz=conditional_rms["p50"],
                    conditional_rms_recordings=conditional_rms["n"],
                    median_original_report_rms_hz=original_rms["p50"],
                    original_report_rms_recordings=original_rms["n"],
                    coordinate_reference=comparator if method == METHOD else METHOD,
                    coordinate_comparisons=deltas["n"],
                    coordinate_comparisons_over_1m=sum(
                        r[f"{comparator}_coordinate_delta_m"] is not None
                        and r[f"{comparator}_coordinate_delta_m"] > 1
                        for r in group
                    ),
                    max_coordinate_delta_m=deltas["max"],
                )
            baseline = methods["baseline"]
            for summary in methods.values():
                for limit in (5, 10):
                    summary[f"passes_no_repair_v5_{limit}pct"] = (
                        summary["published"] >= baseline["published"]
                        and summary["within_5_km"] >= baseline["within_5_km"]
                        and all(
                            summary[k] is not None and summary[k] <= baseline[k] * (1 + limit / 100)
                            for k in ("median_error_km", "p95_error_km")
                        )
                    )
                summaries.append(summary)
    return summaries


def publish_scores(out, refs, records, checkpoints):
    rows = comparison_rows(refs, records, load_rows(checkpoints))
    csv_file(out / "roof-comparison.csv", rows)
    csv_file(out / "roof-distributions.csv", distribution_rows(rows))


def archive_digests(out, receipts, checkpoints):
    files = (
        out / PREDICTIONS,
        receipts / TIMING_RECEIPT,
        receipts / STRESS_RECEIPT,
        *(checkpoints / f"{split}.jsonl.gz" for split in cohorts()),
        corpus.FROZEN / "provenance.json",
    )
    return file_digests(files)


def file_digests(files):
    return {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files}


def check_digests(actual, expected):
    mismatches = sorted(
        k for k in actual.keys() | expected.keys() if actual.get(k) != expected.get(k)
    )
    if mismatches:
        raise ValueError(f"roof archive digest differs for {', '.join(mismatches)}")


def read_archive_receipt(path):
    archive = json.loads(path.read_bytes())
    if (
        not isinstance(archive, dict)
        or archive.get("schema_version") != 1
        or not isinstance(archive.get("files"), dict)
        or any(
            not isinstance(digest, str) or not SHA256.fullmatch(digest)
            for digest in (archive.get("implementation_sha256"), archive.get("kernel_sha256"))
        )
    ):
        raise ValueError("invalid projector roof archive receipt")
    return archive


def save_archive(out, refs, records, receipts, checkpoints, hashes):
    raw = b"".join(encoded(r) + b"\n" for r in ordered_predictions(refs, records))
    write(out / PREDICTIONS, gzip.compress(raw, mtime=0))
    archive = dict(
        schema_version=1,
        implementation_sha256=hashes[0],
        kernel_sha256=hashes[1],
        files=archive_digests(out, receipts, checkpoints),
    )
    write(out / ARCHIVE_RECEIPT, encoded(archive) + b"\n")


def rescore_archive(out, refs, receipts, checkpoints):
    archive = read_archive_receipt(out / ARCHIVE_RECEIPT)
    hashes = (archive["implementation_sha256"], archive["kernel_sha256"])
    check_digests(archive_digests(out, receipts, checkpoints), archive["files"])

    records = read_predictions(out / PREDICTIONS)
    reused = reuse(receipts, hashes, archive=archive, rerun_stale=True)
    for record in ordered_predictions(refs, records):
        ident = record["id"]
        if ident in reused:
            if record != reused[ident]:
                raise ValueError(f"{ident} roof prediction differs from the reused result")
        else:
            validate_confirmation(record, hashes)
    publish_scores(out, refs, records, checkpoints)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--previous", type=Path, help="also check the original paired/stress scratch"
    )
    parser.add_argument("--receipts", type=Path, default=REPORT)
    parser.add_argument("--checkpoints", type=Path, default=CHECKPOINTS)
    parser.add_argument("--work", type=Path, default=SCRATCH / "wide")
    parser.add_argument(
        "--out",
        type=Path,
        help="defaults to the archived report for scoring and WORK/report for a new run",
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_OUT / "inputs")
    parser.add_argument("--cpus", type=int, nargs="+")
    parser.add_argument("--timeout", type=float, default=720)
    parser.add_argument(
        "--score-only",
        action="store_true",
        help="verify saved digests and score without native inputs",
    )
    parser.add_argument("--retry-worker-failures", action="store_true", help="one further attempt")
    args = parser.parse_args()
    refs = roster()
    out = local_output(args.out or (REPORT if args.score_only else args.work / "report"))
    if args.score_only:
        rescore_archive(out, refs, args.receipts, args.checkpoints)
        return
    if not args.cpus or args.timeout <= 0:
        parser.error("choose CPUs and a positive timeout for a new confirmation")
    if out == REPORT.resolve():
        parser.error("use a separate output directory for a new confirmation")
    records, hashes = run_panel(
        refs,
        args.work,
        args.receipts,
        local_output(args.cache),
        args.cpus,
        args.timeout,
        previous=args.previous,
        retry=args.retry_worker_failures,
    )
    save_archive(out, refs, records, args.receipts, args.checkpoints, hashes)
    rescore_archive(out, refs, args.receipts, args.checkpoints)


if __name__ == "__main__":
    main()
