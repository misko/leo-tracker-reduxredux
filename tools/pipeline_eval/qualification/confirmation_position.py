"""Reconstruct complete v5 tracks around the original late-pilot decisions."""

import argparse
import gzip
import json
import os
from collections import defaultdict
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output, write
from ..scoring import validate_result
from ..variants import pilot_confirmation, v5_lean
from .cold_input import CANDIDATE_FIELDS
from .full_v5_check import BULK, REPO, _load_case, _sha
from .pilot_confirmation_trial import HOLDOUT_SEGMENTS, SEGMENTS, SEQUENCES
from .recording_to_v5 import SINGLE_THREAD, bind_request, digest, native_document, save

CASES = ("DS26-0036", "DS29-0082")
FRONTEND = REPO / "reports/2026_11_19_receiver_frontend"
ORDINARY = BULK / "leo-dev/pipeline-eval-20261118/full-v5-check"
SOURCE_NAMES = {"DS26-0036": "native-complete", "DS29-0082": "native-complete-ds29"}
RECEIPTS = {
    "DS26-0036": {
        "trial": "a0393f2d3e71d5d5efd4a8543db97fdd229112ba201d3a203f1fe8c485267f71",
        "alternate": "e7dbe8ca9a42f46064a2fc7154728ef66098525ab46a825e2d25477d216567e6",
    },
    "DS29-0082": {
        "trial": "e96f7117f657dab4604e6b55b7420b1f7bfb0b439c6b58a06e4c9357f6b5b942",
        "alternate": "8cdc7f4b2dfdbf080fbfd1b9777e2d9f9aed788c70c13b640400d8a1a407f01d",
    },
}
SUPPORT = ("segment", "sequence", "visit", "iq_sha256", "status", "reason")
METHOD = "pilot_confirmation"
CONTROL = "ordinary_control"
PARTIAL_BOUNDARY = "Late pilot gate on 112 scheduled visits in a complete ordinary native v5 fit"
CONTROL_BOUNDARY = "Matched ordinary native GLRT on the complete recording through frozen v5"


def verified_ordinary(case):
    """Bind exact ordinary factors and all visit identities to their published authority."""
    case_id = case["id"]
    directory = ORDINARY / SOURCE_NAMES[case_id]
    binding = json.loads((FRONTEND / "ordinary/recording-receipts.json").read_bytes())[
        "recordings"
    ][case_id]
    path = directory / "native.json"
    if _sha(path) != binding["native_sha256"]:
        raise ValueError("ordinary native input differs from its published digest")
    lanes = []
    for lane in range(2):
        with (directory / f"replayed-{lane}.jsonl").open() as stream:
            lanes.append(list(map(json.loads, stream)))
    original = json.loads(path.read_bytes())
    reconstructed, metrics = native_document(case, lanes)
    if (
        original != reconstructed
        or original["source"]["analysis_manifest_sha256"] != binding["analysis_manifest_sha256"]
        or original["source"]["input_manifest_sha256"] != binding["input_manifest_sha256"]
        or original["provenance"]["detector_sha256"] != binding["detector_sha256"]
        or case["request"]["sha256"] != binding["frozen_request_sha256"]
    ):
        raise ValueError("ordinary native authority could not be reproduced")
    visits = {
        record["visit"]: record for lane in lanes for record in lane if record["kind"] == "visit"
    }
    return original, path, visits, metrics


def verify_selection(case, original):
    """Read both locked samples and verify their detector and capture bindings."""
    rows = []
    eligibility = []
    code = _sha(Path(pilot_confirmation.__file__))
    for sample, segments in (("trial", SEGMENTS), ("alternate", HOLDOUT_SEGMENTS)):
        path = FRONTEND / "confirmation" / f"{case['id']}-{sample}.json.gz"
        payload = path.read_bytes()
        if _sha(path) != RECEIPTS[case["id"]][sample]:
            raise ValueError("late-pilot measurement changed after detector qualification")
        receipt = json.loads(gzip.decompress(payload))
        source = original["source"]
        expected = {(segment, sequence) for segment in segments for sequence in SEQUENCES}
        if (
            receipt["case"] != case["id"]
            or receipt["archive_sha256"] != case["native"]["sha256"]
            or "sha256:" + receipt["native_sha256"] != original["provenance"]["detector_sha256"]
            or receipt["source_sha256"]["confirmation"] != code
            or receipt["producer"]["input_manifest_sha256"] != source["input_manifest_sha256"]
            or receipt["sample_rate_hz"] != source["sample_rate_hz"]
            or len(receipt["windows"]) != len(expected)
            or {(w["segment"], w["sequence"]) for w in receipt["windows"]} != expected
        ):
            raise ValueError("late-pilot sample does not bind the original detector and visits")
        rows.extend(receipt["windows"])
        eligibility.append(receipt["summary"]["passed"])
    return rows, all(eligibility)


def decisions(visits, measured):
    """Check exact candidate membership, then keep only original positives' decisions."""
    result = {}
    for row in measured:
        visit = row["visit"]
        original = visits.get(visit)
        if original is None or visit in result or any(row[k] != original[k] for k in SUPPORT):
            raise ValueError("late-pilot measurement does not bind a unique native IQ visit")
        observed = {}
        for measurement in row["candidates"]:
            key = measurement["receiver"], measurement["candidate_rank"]
            if key in observed or type(measurement["confirmation"]["passed"]) is not bool:
                raise ValueError("late-pilot measurement has duplicate or invalid candidates")
            observed[key] = measurement
        originals = {
            (probe["receiver_id"], candidate["candidate_rank"]): candidate
            for probe in original["probes"]
            for candidate in probe["candidates"]
        }
        if observed.keys() != originals.keys() or any(
            originals[key] != {field: observed[key][field] for field in CANDIDATE_FIELDS}
            for key in originals
        ):
            raise ValueError("late-pilot measurement does not match the complete native candidates")
        result[visit] = {
            key: observed[key]["confirmation"]["passed"]
            for key, candidate in originals.items()
            if candidate["passed_fractional_margin_gate"]
        }
    return result


def apply_gate(original, visits, gate, identity, boundary):
    """Remove rejected proposals without modifying the native carrier or evidence fields."""
    rejected = defaultdict(set)
    checked = 0
    for visit, values in gate.items():
        expected = {
            (probe["receiver_id"], candidate["candidate_rank"])
            for probe in visits[visit]["probes"]
            for candidate in probe["candidates"]
            if candidate["passed_fractional_margin_gate"]
        }
        if values.keys() != expected or any(type(passed) is not bool for passed in values.values()):
            raise ValueError("gate needs exactly one decision for every original positive")
        checked += len(values)
        for (receiver, rank), passed in values.items():
            if not passed:
                rejected[visit, receiver].add(rank)

    probes = []
    for probe in original["source"]["probes"]:
        ranks = rejected.get((probe["visit_index"], probe["receiver_id"]))
        if ranks:
            retained = [c for c in probe["candidates"] if c["candidate_rank"] not in ranks]
            probe = dict(probe, candidates=retained)
        probes.append(probe)
    analysis = digest([identity, original["source"]["analysis_manifest_sha256"], probes])
    document = dict(
        original,
        source=dict(original["source"], probes=probes, analysis_manifest_sha256=analysis),
        provenance=dict(original["provenance"], run_id="replay-" + analysis[7:39], scope=boundary),
    )
    total_removed = sum(map(len, rejected.values()))
    metrics = dict(
        scheduled_gate_visits=len(gate),
        valid_gate_visits=sum(visits[i]["status"] == "processed" for i in gate),
        changed_visits=len({visit for visit, _ in rejected}),
        changed_probe_rows=len(rejected),
        compared_original_positive_candidates=checked,
        confirmed_original_positive_candidates=checked - total_removed,
        removed_original_positive_candidates=total_removed,
    )
    return document, metrics


def fit(case, native_path, directory, method, boundary, metrics):
    directory.mkdir(parents=True, exist_ok=False)
    bound = bind_request(case, native_path, directory / "experimental-request.json")
    implementation = _sha(Path(__file__))
    started = perf_counter()
    result = v5_lean.run(bound, directory / "position")
    elapsed = perf_counter() - started
    result["boundary"] = boundary
    result["metrics"].update(metrics, position_attempted=True)
    validate_result(result)
    row = dict(
        id=case["id"],
        method=method,
        input_sha256=bound["native_sha256"],
        implementation_sha256=implementation,
        worker_wall_s=elapsed,
        result=result,
    )
    save(directory / "receipt.json", row)
    print(case["id"], method, result["status"], round(elapsed, 2), flush=True)
    return row


def position_pair(case_id, work):
    case = _load_case(case_id)
    original, path, visits, metrics = verified_ordinary(case)
    measured, passed = verify_selection(case, original)
    gate = decisions(visits, measured)
    identity = ["late-pilot-confirmation-partial", RECEIPTS[case_id]]
    document, intervention = apply_gate(original, visits, gate, identity, PARTIAL_BOUNDARY)
    save(work / "partial-native.json", document)
    candidate = fit(
        case,
        work / "partial-native.json",
        work / METHOD,
        METHOD,
        PARTIAL_BOUNDARY,
        dict(
            metrics,
            **intervention,
            positive_candidates=metrics["positive_candidates"]
            - intervention["removed_original_positive_candidates"],
            detector_sample_advancement_passed=passed,
            ordinary_input_sha256="sha256:" + _sha(path),
            confirmation_receipt_sha256=RECEIPTS[case_id],
        ),
    )
    control = fit(case, path, work / CONTROL, CONTROL, CONTROL_BOUNDARY, metrics)
    return candidate, control


def publish(work, output):
    publications = {}
    for method, name in ((METHOD, "positions.jsonl.gz"), (CONTROL, "control-positions.jsonl.gz")):
        rows = [json.loads((work / case / method / "receipt.json").read_bytes()) for case in CASES]
        for case_id, row in zip(CASES, rows, strict=True):
            if row["id"] != case_id or row["method"] != method:
                raise ValueError("position receipt belongs to a different recording or method")
            bind_published_source(row)
            row["variant"] = "partial-visits" if method == METHOD else "matched-ordinary"
        publications[name] = rows
    for candidate, control in zip(*publications.values(), strict=True):
        if candidate["source_archive_sha256"] != control["source_archive_sha256"]:
            raise ValueError("intervention and ordinary control do not share the sealed source")
    for name, rows in publications.items():
        write(output / name, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def bind_published_source(row):
    validate_result(row["result"])
    ordinary = (
        row["input_sha256"]
        if row["method"] == CONTROL
        else row["result"]["metrics"]["ordinary_input_sha256"]
    )
    row["source_archive_sha256"] = ordinary.removeprefix("sha256:")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--publish", type=Path)
    args = parser.parse_args()
    work = local_output(args.work)
    if work.is_relative_to(BULK):
        parser.error("use replay scratch outside the data archive")
    if args.publish is not None and args.case is None:
        publish(work, local_output(args.publish))
        return
    if args.case is None or args.publish is not None:
        parser.error("select one replay case or publish the two completed cases")
    if len(os.sched_getaffinity(0)) != 1 or any(
        os.environ.get(key) != value for key, value in SINGLE_THREAD.items()
    ):
        parser.error("pin numerical replay to one CPU and one thread per numerical runtime")
    case_work = work / args.case
    case_work.mkdir(parents=True, exist_ok=False)
    position_pair(args.case, case_work)


if __name__ == "__main__":
    main()
