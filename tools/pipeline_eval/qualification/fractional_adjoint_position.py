"""Check the adjoint qualification and run paired partial-IQ position fits."""

import argparse
import gzip
import json
import os
from pathlib import Path

from ..__main__ import THREAD_ENV, encoded, local_output, read_predictions, write
from ..scoring import distribution, validate_result
from ..variants import anchor_receiver, v5_lean
from . import spectral_position
from .conditioned_cfo_position import write_rows
from .fractional_adjoint_eval import CASE_CPUS, METHOD, SCHEDULE, sources
from .full_v5_check import BULK, PRODUCERS, _load_case, _measure, _sha
from .recording_to_v5 import digest, save
from .refine_bank_position import CONTROL_PATH

CONTROL = "fractional_adjoint_capture_control"
STAGE = "Continuous fractional GLRT64 scoring on authenticated 20 ms visits"
BOUNDARY = "Partial adjoint fractional GLRT IQ replay plus archive to full no-repair v5"


def read_panel(case, report):
    expected = {p.name: _sha(p) for p in sources()}
    blocks, hashes, implementations = {}, {}, set()
    for split, (segment, sequences) in SCHEDULE.items():
        path = report / f"{case['id']}-{split}.json.gz"
        block = json.loads(gzip.decompress(path.read_bytes()))
        if (
            (block["case"], block["split"], block["segment"]) != (case["id"], split, segment)
            or block["source_sha256"] != expected
            or block["producer"]["run_id"] != case["run_id"]
            or tuple(r["sequence"] for r in block["rows"]) != sequences
        ):
            raise ValueError("Detector receipt does not bind the frozen producer and roster")
        implementations.add(digest([block["producer"], block["library_sha256"]]))
        blocks[split], hashes[split] = block, _sha(path)
    if len(implementations) != 1:
        raise ValueError("The three splits used different locked kernels")
    return blocks, hashes, digest(expected)


def qualify(blocks):
    held = [blocks[split] for split in ("early", "late")]
    totals = {m: {k: sum(b["summary"]["totals"][m][k] for b in held)
                  for k in ("full_cpu_s", "continuous_cpu_s")} for m in (METHOD, "control")}
    rows = [r for b in blocks.values() for r in b["rows"]]
    controls = blocks["development"]["controls"]
    approved = all(r["comparison"]["passed"] and r["stable"] and r["equal_status"]
                   for r in (*rows, *controls.values()))
    capture = all(r["matches_original_control"] for r in rows)
    synthetic = set(controls) == {"plant", "faint", "adjacent", "empty", "noise"}
    return dict(
        eligible_for_position=approved and capture and synthetic,
        captured=len(rows), valid=sum(r["policy_status"] == "processed" for r in rows),
        control_matches_installed=capture, passed_field_checks=approved,
        max_changed_score=max(e for r in rows for e in r["comparison"]["max_error"].values()),
        changed_candidates=sum(len(r["comparison"]["changed_negative_fields"]) for r in rows),
        held_cpu_s=totals,
    )


def gate(report):
    methods, summaries, stage = (METHOD, "control"), {}, []
    fields = ("full_cpu_s", "continuous_cpu_s")
    for case_id in PRODUCERS:
        case = _load_case(case_id)
        blocks, hashes, source = read_panel(case, report)
        summary = qualify(blocks)
        summaries[case_id] = summary
        result = dict(
            status="withheld", boundary=STAGE, reason="Detector timing and field checks only.",
            metrics={"position_attempted": False, **summary},
            arms={arm: {"latlon": None} for arm in v5_lean.ARMS},
        )
        validate_result(result)
        stage.append(dict(
            id=case_id, method=METHOD, result=result, implementation_sha256=source,
            input_sha256=digest(hashes), source_archive_sha256=case["native"]["sha256"],
        ))
    totals = {m: {k: sum(r["held_cpu_s"][m][k] for r in summaries.values())
                  for k in fields} for m in methods}
    saving = {k: 1 - totals[METHOD][k] / totals["control"][k] for k in fields}
    eligible = all(r["eligible_for_position"] for r in summaries.values())
    quality = dict(
        eligible_for_position=eligible, pooled_cpu_s=totals, pooled_fraction_saved=saving,
        material_timing_gate=eligible and saving["full_cpu_s"] >= .03
        and saving["continuous_cpu_s"] >= .40, cases=summaries,
    )
    write(report / "qualification.json", encoded(quality) + b"\n")
    write_rows(report / "detector-stage.jsonl.gz", stage)
    if not eligible:
        for row in stage:
            row["result"]["reason"] = "The detector payload or positive factor check failed."
        write_rows(report / "positions.jsonl.gz", stage)
    return quality


def _positive_probes(probes):
    return [dict(p, candidates=[c for c in p["candidates"] if c["passed_fractional_margin_gate"]])
            for p in probes]


def compose(case, archive, rows, producer, source, library):
    audit = _measure(case, rows, archive["source"]["sample_rate_hz"])
    if not audit["archive_exclusions_equal"] or audit["different_probe_keys"]:
        raise ValueError("Accelerated control did not reproduce the archived input factors")
    replay = dict(rows=rows, producer=producer, source_sha256=source, kernel_sha256=library,
                  archive_audit=audit)
    composite, changed = anchor_receiver.splice_probes(archive, replay)
    if _positive_probes(composite["source"]["probes"]) != _positive_probes(
        archive["source"]["probes"]
    ):
        raise ValueError("Adjoint changed a positive factor used in track preparation")
    composite["provenance"]["scope"] = BOUNDARY
    return composite, changed


def position(case_id, report, work):
    case = _load_case(case_id)
    blocks, hashes, source = read_panel(case, report)
    status = qualify(blocks)
    if not status["eligible_for_position"]:
        raise ValueError("Detector evidence is not eligible for a fitted position")
    archive_path = BULK / case["native"]["path"]
    sha = case["native"]["sha256"]
    baseline = read_predictions(CONTROL_PATH)[case_id]
    if _sha(archive_path) != sha or baseline["input_sha256"] != f"sha256:{sha}":
        raise ValueError("Capture-era control does not bind this archive")
    archive = json.loads(archive_path.read_bytes())
    rows = [r for split in ("early", "late") for r in blocks[split]["rows"]]
    dev = blocks["development"]
    composite, changed = compose(case, archive, rows, dev["producer"], source,
                                 dev["library_sha256"]["adjoint"])
    work.mkdir(parents=True, exist_ok=False)
    path = work / "partial-iq-native.json"
    save(path, composite)
    fit = spectral_position.fit(case, path, work / "fit", METHOD)
    spectral_position.verify_pair(baseline, fit)
    valid = sum(r["policy_status"] == "processed" for r in rows)
    fit["result"]["boundary"] = BOUNDARY
    fit["result"]["metrics"].update(
        scheduled_visits=len(rows), fresh_iq_visits=valid,
        archived_valid_visits=archive["provenance"]["processed_windows"] - valid,
        replayed_capture_exclusions=len(rows) - valid, modified_negative_probe_rows=changed,
        identical_positive_factors=True, identical_prepared_arcs=True,
        control_input_sha256=baseline["input_sha256"],
    )
    fit.update(
        variant="partial-iq-fractional-adjoint", source_archive_sha256=sha,
        implementation_sha256=source, detector_receipts_sha256=hashes,
        control_receipt_sha256=_sha(CONTROL_PATH), position_error_km=baseline["position_error_km"],
    )
    baseline["method"] = CONTROL
    for row in (fit, baseline):
        validate_result(row["result"])
        write(report / f"{case_id}-{row['method']}.json", encoded(row) + b"\n")


def package(report):
    rows = {m: [] for m in (METHOD, CONTROL)}
    for case_id in PRODUCERS:
        for method in rows:
            row = json.loads((report / f"{case_id}-{method}.json").read_bytes())
            if (row["id"], row["method"]) != (case_id, method):
                raise ValueError("Unexpected partial position receipt")
            rows[method].append(row)
        spectral_position.verify_pair(rows[CONTROL][-1], rows[METHOD][-1])
    write_rows(report / "positions.jsonl.gz", rows[METHOD])
    write_rows(report / "control-positions.jsonl.gz", rows[CONTROL])
    errors = {m: {a: distribution(r["position_error_km"][a] for r in group)
                  for a in v5_lean.ARMS} for m, group in rows.items()}
    write(report / "error-distributions.json", encoded(errors) + b"\n")


def seal_figures(report):
    """Attach exact catalogue identities to copies of both archived position bundles."""
    inputs = {case_id: _load_case(case_id) for case_id in PRODUCERS}
    for case in inputs.values():
        if _sha(BULK / case["catalog"]["path"]) != case["catalog"]["sha256"]:
            raise ValueError("Frozen catalogue bytes changed")
    originals = ("positions.jsonl.gz", "control-positions.jsonl.gz")
    figures = tuple(f"figure-{name}" for name in originals)
    for name, figure in zip(originals, figures, strict=True):
        records = read_predictions(report / name)
        if set(records) != set(inputs):
            raise ValueError("Unexpected archive roster in the position series")
        plotted = []
        for case_id, case in inputs.items():
            row = records[case_id]
            if row["source_archive_sha256"] != case["native"]["sha256"]:
                raise ValueError("Position series does not bind the frozen native archive")
            plotted.append(dict(row, catalog_sha256=case["catalog"]["sha256"]))
        write_rows(report / figure, plotted)
    files = (*originals, *figures, "qualification.json", "error-distributions.json",
             "detector-stage.jsonl.gz", *(
                 f"{case_id}-{split}.json.gz" for case_id in PRODUCERS for split in SCHEDULE
             ))
    lock = dict(cases=list(PRODUCERS), files={name: _sha(report / name) for name in files})
    write(report / "prediction-lock.json", encoded(lock) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--case", choices=PRODUCERS)
    modes.add_argument("--gate", action="store_true")
    modes.add_argument("--package", action="store_true")
    modes.add_argument("--seal-figures", action="store_true")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    report = local_output(args.report)
    if args.gate:
        print(encoded(gate(report)).decode())
    elif args.package:
        package(report)
    elif args.seal_figures:
        seal_figures(report)
    else:
        single = all(os.environ.get(k) == "1" for k in THREAD_ENV)
        if not single or os.sched_getaffinity(0) != {CASE_CPUS[args.case]} or args.work is None:
            parser.error("pin the case CPU, use one numerical thread, and provide a work path")
        work = local_output(args.work)
        if any(p.is_relative_to(BULK / "leo") for p in (report, work)):
            parser.error("choose output directories outside the capture archive")
        position(args.case, report, work)


if __name__ == "__main__":
    main()
