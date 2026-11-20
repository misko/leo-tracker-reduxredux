"""Validate the conditioned score trial and fit matched partial-IQ positions."""

import argparse
import gzip
import json
import os
from pathlib import Path

from ..__main__ import THREAD_ENV, encoded, local_output, read_predictions, write
from ..scoring import distribution, validate_result
from ..variants import conditioned_cfo_bank, v5_lean
from . import conditioned_cfo_eval, spectral_position
from .conditioned_cfo_eval import CASE_CPUS, METHOD, SCHEDULE
from .full_v5_check import BULK, PRODUCERS, _load_case, _sha
from .recording_to_v5 import digest, save
from .refine_bank_position import CONTROL_PATH

CONTROL = "conditioned_cfo_capture_control"
STAGE = "Conditioned CFO bank on authenticated capture-era 20 ms visits"
BOUNDARY = "Partial conditioned-CFO IQ replay plus capture-era archive to full no-repair v5"


def read_panel(case, report):
    source = (Path(conditioned_cfo_eval.__file__), Path(conditioned_cfo_bank.__file__),
              conditioned_cfo_bank.SOURCE)
    expected = {p.name: _sha(p) for p in source}
    ids, stage_hashes, blocks = {}, {}, {}
    for split, (segment, sequences) in SCHEDULE.items():
        path = report / f"{case['id']}-{split}.json.gz"
        block = json.loads(gzip.decompress(path.read_bytes()))
        if (
            (block["case"], block["split"], block["segment"]) != (case["id"], split, segment)
            or block["source_sha256"] != expected
            or block["producer"]["run_id"] != case["run_id"]
            or tuple(row["sequence"] for row in block["rows"]) != sequences
        ):
            raise ValueError("Conditioning receipt does not bind the frozen producer and roster")
        ids[split] = digest([block["producer"], block["library_sha256"]])
        stage_hashes[split] = _sha(path)
        blocks[split] = block
    if len(set(ids.values())) != 1:
        raise ValueError("All three rosters must use the same producer and compiled kernels")
    return blocks, stage_hashes, digest(expected)


def qualify(blocks):
    totals = {m: {"full_cpu_s": 0.0, "conditioned_cpu_s": 0.0} for m in ("control", METHOD)}
    rows = [r for block in blocks.values() for r in block["rows"]]
    for split in ("holdout", "extension"):
        by_mode = blocks[split]["summary"]["timing"]
        for m, values in totals.items():
            for key in values:
                values[key] += by_mode[m]["totals"][key]
    has_original = all(r["matches_original_payload"] for r in rows)
    exact = has_original and all(
        r["stable"] and r["equal_status"] and r["comparison"]["exact_payload"] for r in rows
    )
    audited = [
        a for block in blocks.values() for a in (block["dense_audit"] or {}).get("rows", ())
        if a["fallback"] is None
    ]
    enclosure = bool(audited) and all(
        row["same_winner"] and row["max_grid_error"] <= row["error_bound"]
        and row["repaired_score_error"] <= 1e-12 for row in audited
    )
    test = blocks["development"]["controls"]
    synthetic = set(test) == {"plant", "faint", "empty", "adjacent"} and all(
        row["comparison"]["exact_payload"] for row in test.values()
    )
    if synthetic:
        plant = test["plant"]["positive_winners"][METHOD]
        synthetic = len(plant) == 2 and all(
            row["fractional"]["winner"] is not None and row["fractional"]["winner"]["epoch"] == 731
            for row in plant.values()
        )
    saves = {k: 1 - totals[METHOD][k] / totals["control"][k] if totals["control"][k] else None
             for k in totals[METHOD]}
    passed = exact and enclosure and synthetic and all(
        block["summary"]["valid"] > 0 for block in blocks.values()
    )
    return dict(
        exact_archive_payloads=exact, complete_audited_enclosure=enclosure,
        synthetic_parity=synthetic, eligible_for_position=passed,
        rows=len(rows), valid=sum(r["policy_status"] == "processed" for r in rows),
        held_cpu_s=totals, held_fraction_saved=saves,
        score_maps_audited=len(audited),
        largest_approximation_error=max((r["max_grid_error"] for r in audited), default=None),
        largest_repaired_score_error=max(
            (r["repaired_score_error"] for r in audited), default=None,
        ),
    )


def write_rows(path, rows):
    raw = b"".join(encoded(row) + b"\n" for row in rows)
    write(path, gzip.compress(raw, mtime=0))


def gate(report):
    summaries, records = {}, []
    for case_id in PRODUCERS:
        case = _load_case(case_id)
        blocks, hashes, impl = read_panel(case, report)
        status = qualify(blocks)
        summaries[case_id] = status
        result = dict(
            status="withheld", boundary=STAGE,
            reason="This receipt covers detector timing and payload parity on the sampled visits.",
            arms={arm: {"latlon": None} for arm in v5_lean.ARMS},
            metrics={"position_attempted": False, **status},
        )
        validate_result(result)
        records.append(dict(
            id=case_id, method=METHOD, source_archive_sha256=case["native"]["sha256"],
            input_sha256=digest(hashes), implementation_sha256=impl, result=result,
        ))
    pooled = {m: {k: sum(r["held_cpu_s"][m][k] for r in summaries.values())
                  for k in ("full_cpu_s", "conditioned_cpu_s")} for m in ("control", METHOD)}
    save_fractions = {k: 1 - pooled[METHOD][k] / pooled["control"][k]
                      for k in pooled[METHOD] if pooled["control"][k]}
    causal = all(r["eligible_for_position"] for r in summaries.values())
    material = causal and save_fractions["full_cpu_s"] >= 0.10 and (
        save_fractions["conditioned_cpu_s"] >= 0.60 and all(
            r["held_fraction_saved"]["full_cpu_s"] >= 0.05 for r in summaries.values()
        )
    )
    summary = dict(eligible_for_position=causal, passed_material_gate=material,
                   pooled_fraction_saved=save_fractions, pooled_cpu_s=pooled, cases=summaries)
    write(report / "qualification.json", encoded(summary) + b"\n")
    write_rows(report / "detector-stage.jsonl.gz", records)
    if not causal:
        for row in records:
            row["result"]["reason"] = "Detector parity or score enclosure condition did not pass."
        write_rows(report / "positions.jsonl.gz", records)
    return summary


def position(case_id, report, work):
    case = _load_case(case_id)
    blocks, hashes, impl = read_panel(case, report)
    qualified = qualify(blocks)
    if not qualified["eligible_for_position"]:
        raise ValueError("Detector receipt lacks exact-payload replay for positioning")
    archive_path = BULK / case["native"]["path"]
    archive_sha = case["native"]["sha256"]
    baseline = read_predictions(CONTROL_PATH)[case_id]
    if (
        _sha(archive_path) != archive_sha or baseline["source_archive_sha256"] != archive_sha
        or baseline["input_sha256"] != f"sha256:{archive_sha}"
    ):
        raise ValueError("Capture-era control did not consume the frozen native document")
    archive = json.loads(archive_path.read_bytes())
    rows = [row for split in SCHEDULE for row in blocks[split]["rows"]]
    measurement = dict(
        producer=blocks["development"]["producer"], rows=rows, source_sha256=impl,
        kernel_sha256=blocks["development"]["library_sha256"]["conditioned"],
    )
    composite, audit = spectral_position.compose(case, archive, measurement)
    composite["provenance"]["scope"] = BOUNDARY
    work.mkdir(parents=True, exist_ok=False)
    path = work / "partial-iq-native.json"
    save(path, composite)
    fit = spectral_position.fit(case, path, work / "fit", METHOD)
    spectral_position.verify_pair(baseline, fit)
    result = fit["result"]
    result["boundary"] = BOUNDARY
    result["metrics"].update(
        scheduled_visits=len(rows), fresh_iq_visits=qualified["valid"],
        replayed_capture_exclusions=len(rows) - qualified["valid"],
        archived_valid_visits=archive["provenance"]["processed_windows"] - qualified["valid"],
        fresh_receiver_probe_rows=audit["exact_probe_rows"],
        control_input_sha256=baseline["input_sha256"],
        detector_cpu_s=sum(r["timings"][METHOD][0]["full_cpu_s"] for r in rows),
        detector_wall_s=sum(r["timings"][METHOD][0]["full_wall_s"] for r in rows),
        identical_capture_era_factors=True, identical_prepared_arcs=True,
    )
    fit.update(
        variant="partial-iq-conditioned-cfo", source_archive_sha256=archive_sha,
        implementation_sha256=impl, detector_receipts_sha256=hashes,
        control_receipt_sha256=_sha(CONTROL_PATH), position_error_km=baseline["position_error_km"],
    )
    baseline["method"] = CONTROL
    for row in (fit, baseline):
        validate_result(row["result"])
        write(report / f"{case_id}-{row['method']}.json", encoded(row) + b"\n")


def package(report):
    records = {m: [] for m in (METHOD, CONTROL)}
    for case_id in PRODUCERS:
        for method in records:
            row = json.loads((report / f"{case_id}-{method}.json").read_bytes())
            if row["id"] != case_id or row["method"] != method:
                raise ValueError("Unexpected matched position receipt")
            records[method].append(row)
        spectral_position.verify_pair(records[CONTROL][-1], records[METHOD][-1])
    write_rows(report / "positions.jsonl.gz", records[METHOD])
    write_rows(report / "control-positions.jsonl.gz", records[CONTROL])
    errors = {m: {a: distribution(r["position_error_km"][a] for r in rows)
                  for a in v5_lean.ARMS} for m, rows in records.items()}
    write(report / "error-distributions.json", encoded(errors) + b"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--case", choices=PRODUCERS)
    action.add_argument("--gate", action="store_true")
    action.add_argument("--package", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    report = local_output(args.report)
    if args.gate:
        print(encoded(gate(report)).decode(), flush=True)
    elif args.package:
        package(report)
    else:
        single = all(os.environ.get(k) == "1" for k in THREAD_ENV)
        if args.work is None or os.sched_getaffinity(0) != {CASE_CPUS[args.case]} or not single:
            parser.error("provide a work path, pin the designated CPU and set one numerical thread")
        work = local_output(args.work)
        if any(p.is_relative_to(BULK / "leo") for p in (work, report)):
            parser.error("choose a work and report directory outside the capture archive")
        position(args.case, report, work)


if __name__ == "__main__":
    main()
