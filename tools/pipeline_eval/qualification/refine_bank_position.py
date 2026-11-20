"""Confirm the fused GLRT on two paired partial-IQ positions."""

import argparse
import gzip
import json
import os
from pathlib import Path

from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, read_predictions, write
from ..scoring import distribution, validate_result
from ..variants import pilot_kernel, refine_bank, v5_lean
from . import refine_bank_eval, spectral_position
from .full_v5_check import BULK, PRODUCERS, _load_case, _sha
from .recording_to_v5 import digest, save
from .spectral_grid_eval import SCHEDULE, SEQUENCES

METHOD = "refine_bank"
CONTROL = "refine_bank_capture_control"
BOUNDARY = "Partial fused-refinement IQ replay plus capture-era archive to full no-repair v5"
CONTROL_PATH = (ROOT / "reports/2026_11_19_position_atlas/spectral-grid/control-positions.jsonl.gz")


def assemble(case, report):
    """Use only exact archived outputs of the already qualified candidate execution."""
    case_id = case["id"]
    stage_hashes, libraries, all_rows = {}, set(), []
    producer = None
    sources = (Path(refine_bank_eval.__file__), Path(refine_bank.__file__),
               refine_bank.SOURCE, pilot_kernel.SOURCE)
    source_hashes = {p.name: _sha(p) for p in sources}
    for split, segment in SCHEDULE.items():
        path = report / f"{case_id}-{split}.json.gz"
        block = json.loads(gzip.decompress(path.read_bytes()))
        if (
            (block["case"], block["split"], block["segment"]) != (case_id, split, segment)
            or block["source_sha256"] != source_hashes
            or block["producer"]["run_id"] != case["run_id"]
            or (producer is not None and block["producer"] != producer)
            or tuple(row["sequence"] for row in block["rows"]) != SEQUENCES
            or not block["summary"]["exact"] or not block["summary"]["original"]
        ):
            raise ValueError("Fused GLRT trial does not match the original authenticated panel")
        timing = block["summary"]["timing"]
        if split == "holdout" and (
            timing[METHOD]["totals"]["full_cpu_s"] >= timing["control"]["totals"]["full_cpu_s"]
        ):
            raise ValueError("Fused GLRT did not reduce held-out full detector CPU")
        for row in block["rows"]:
            if (not row["stable"] or not row["equal_status"]
                    or not row["comparison"]["exact_payload"]
                    or not row["matches_original_payload"] or not row["iq_sha256"]):
                raise ValueError("Fused GLRT output did not preserve the full archived payload")
            all_rows.append(dict(row, split=split, segment=segment))
        stage_hashes[split] = _sha(path)
        producer = block["producer"]
        libraries.add(block["library_sha256"])
    if len(libraries) != 1:
        raise ValueError("Qualification used different refinement kernels")
    return dict(
        case=case_id, producer=producer, rows=all_rows, quality_receipt_sha256=stage_hashes,
        source_sha256=digest(source_hashes), kernel_sha256=libraries.pop(),
    )


def position(case_id, report, work):
    case = _load_case(case_id)
    source_archive = BULK / case["native"]["path"]
    original_sha = case["native"]["sha256"]
    control = read_predictions(CONTROL_PATH)[case_id]
    if (
        _sha(source_archive) != original_sha
        or control["source_archive_sha256"] != original_sha
        or control["input_sha256"] != f"sha256:{original_sha}"
        or control["method"] != "spectral_grid_capture_control"
    ):
        raise ValueError("Existing fresh control does not bind the capture-era source for this fit")
    measurement = assemble(case, report)
    archive = json.loads(source_archive.read_bytes())
    composite, audit = spectral_position.compose(case, archive, measurement)
    composite["provenance"]["scope"] = BOUNDARY
    work.mkdir(parents=True, exist_ok=False)
    native_path = work / "partial-iq-native.json"
    save(native_path, composite)
    trial = spectral_position.fit(case, native_path, work / "fit", METHOD)
    spectral_position.verify_pair(control, trial)
    rows = measurement["rows"]
    valid = sum(row["policy_status"] == "processed" for row in rows)
    counts = archive["provenance"]
    result = trial["result"]
    result["boundary"] = BOUNDARY
    result["metrics"].update(
        scheduled_visits=len(rows), fresh_iq_visits=valid,
        replayed_capture_exclusions=len(rows) - valid,
        archived_valid_visits=counts["processed_windows"] - valid,
        recording_visits=counts["window_count"],
        fresh_receiver_probe_rows=audit["exact_probe_rows"],
        detector_cpu_s=sum(row["timings"][METHOD][0]["full_cpu_s"] for row in rows),
        detector_wall_s=sum(row["timings"][METHOD][0]["full_wall_s"] for row in rows),
        control_input_sha256=control["input_sha256"],
        identical_capture_era_factors=True, identical_prepared_arcs=True,
    )
    trial.update(
        variant="partial-iq-refine-bank", source_archive_sha256=original_sha,
        implementation_sha256=measurement["source_sha256"],
        detector_receipts_sha256=measurement["quality_receipt_sha256"],
        control_receipt_sha256=_sha(CONTROL_PATH),
        position_error_km=control["position_error_km"],
    )
    control["method"] = CONTROL
    for row in (trial, control):
        validate_result(row["result"])
        write(report / f"{case_id}-{row['method']}.json", encoded(row) + b"\n")


def package(report):
    names = {METHOD: "positions", CONTROL: "control-positions"}
    records = {method: [] for method in names}
    for case_id in PRODUCERS:
        for method in names:
            row = json.loads((report / f"{case_id}-{method}.json").read_bytes())
            if row["id"] != case_id or row["method"] != method:
                raise ValueError("Unexpected position receipt")
            records[method].append(row)
        spectral_position.verify_pair(records[CONTROL][-1], records[METHOD][-1])
    for method, rows in records.items():
        write(report / f"{names[method]}.jsonl.gz", gzip.compress(
            b"".join(encoded(r) + b"\n" for r in rows), mtime=0,
        ))
    errors = {method: {
        arm: distribution(r["position_error_km"][arm] for r in rows) for arm in v5_lean.ARMS
    } for method, rows in records.items()}
    write(report / "error-distributions.json", encoded(errors) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--case", choices=PRODUCERS)
    modes.add_argument("--package", action="store_true")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    report = local_output(args.report)
    if args.package:
        package(report)
        return
    pinned = os.sched_getaffinity(0) == {refine_bank_eval.CASE_CPUS[args.case]}
    single_thread = all(os.environ.get(key) == "1" for key in THREAD_ENV)
    if args.work is None or not pinned or not single_thread:
        parser.error("provide a work directory, pin the designated CPU, and set one thread")
    work = local_output(args.work)
    if report.is_relative_to(BULK / "leo") or work.is_relative_to(BULK / "leo"):
        parser.error("choose output outside the capture archive")
    position(args.case, report, work)


if __name__ == "__main__":
    main()
