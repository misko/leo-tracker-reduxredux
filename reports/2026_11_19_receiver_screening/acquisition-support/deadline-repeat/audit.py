"""Render the primary and repeat observations from the two sealed study authorities."""

import argparse
import gzip
import json
from pathlib import Path

from tools.pipeline_eval import figure_books, iq_comparison_results, whole_iq
from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification.full_held_scores import held_references
from tools.pipeline_eval.qualification.full_v5_check import _sha
from tools.pipeline_eval.qualification.phase_support_results import pack
from tools.pipeline_eval.qualification.prefix_figures import csv_file
from tools.pipeline_eval.qualification.whole_band_results import attempt
from tools.pipeline_eval.scoring import ARMS

REPORT = Path(__file__).resolve().parent
PRIMARY = Path("/srv/bulk/leo-dev/scout-comparison-l7wQ2aPF/run")
PRIMARY_SHA = "2fa56ef979d8f36fa44cf530b3db0394ca61f37186cada08628282af43bfd0fc"
CASES = ["DS29-0082", "DS26-0237"]
BRANCHES = ("control", "candidate")
ABI_INPUTS = (
    "receiver",
    "receiver_files",
    "native_sources",
    "memory_max",
    "swap_max",
    "limit_s",
    "programs",
)


def verify_sources(primary, repeat):
    if set(repeat["cases"]) != set(CASES):
        raise ValueError("Wrong deadline repeat roster")
    for name in ABI_INPUTS:
        if primary[name] != repeat[name]:
            raise ValueError(f"Changed repeat authority: {name}")
    for mode in BRANCHES:
        for key in ("path", "sha256"):
            if primary["detectors"][mode][key] != repeat["detectors"][mode][key]:
                raise ValueError(f"Changed detector: {mode}")
    for case in CASES:
        original = {k: v for k, v in primary["cases"][case].items() if k != "cohort"}
        measured = {k: v for k, v in repeat["cases"][case].items() if k != "cohort"}
        if original != measured:
            raise ValueError(f"Changed paired repeat input: {case}")


def v5_rows(references):
    for reference in references:
        for mode in ("baseline", "selective-gap", "omitted-track-one", "omitted-tracks"):
            arms = reference["reference"][mode]
            for arm in ARMS:
                fit = arms[arm]
                yield dict(
                    id=reference["id"],
                    mode=mode,
                    arm=arm,
                    status=fit["status"],
                    error_km=fit.get("error_km"),
                    rf_rms_hz=fit.get("rf_rms_hz"),
                    archived_wall_s=fit.get("wall_s"),
                )


def relocated_request_equal(original, repeated, original_dir, repeat_dir):
    old_input = Path(original["job"]["native_input"]["path"])
    old_output = Path(original["job"]["output_root"])
    original["job"]["native_input"]["path"] = str(repeat_dir / old_input.relative_to(original_dir))
    original["job"]["output_root"] = str(repeat_dir / old_output.relative_to(original_dir))
    return original == repeated


def audit(primary, report, repeat_work):
    primary_lock_path = whole_iq.checked(primary / "source-lock.json", PRIMARY_SHA)
    if (primary / "source-lock.sha256").read_text().strip() != PRIMARY_SHA:
        raise ValueError("Primary audit seal changed")
    older = whole_iq.read(primary_lock_path)
    seal = iq_comparison_results.sealed(report)
    new = whole_iq.read(report / "source-lock.json")
    verify_sources(older, new)
    primary_rows, primary_resources, receipts = [], {}, {}
    for case in CASES:
        data = primary_resources[case] = {}
        custody = receipts[case] = {}
        for branch in BRANCHES:
            path = primary / case / branch
            row, data[branch], _ = attempt(
                primary, case, branch, older, method=f"scout-primary-audit_{branch}"
            )
            primary_rows.append(row)
            service = data[branch]["service"]
            log = whole_iq.checked(path / "service.log", service["log_sha256"])
            custody[branch] = dict(
                files={
                    name: _sha(path / name)
                    for name in (
                        "plan.json",
                        "service.json",
                        "service.log",
                        "raw.json",
                        "end.json",
                        "position.json",
                    )
                    if (path / name).is_file()
                },
                phase_messages=[
                    line for line in log.read_text().splitlines() if line.startswith("stage:")
                ],
            )
    prior = {(r["id"], r["method"].rsplit("_", 1)[1]): r for r in primary_rows}
    expected = {("DS29-0082", "control"), ("DS26-0237", "candidate")}
    timed = {key for key, row in prior.items() if row["result"]["status"] == "timed_out"}
    if timed != expected:
        raise ValueError("Primary deadline outcomes no longer select the registered pair")
    present = [
        json.loads(line)
        for line in gzip.decompress((report / "positions.jsonl.gz").read_bytes()).splitlines()
    ]
    recent = {(r["id"], r["method"].rsplit("_", 1)[1]): r for r in present}
    if recent.keys() != prior.keys() or sorted(seal["cases"]) != sorted(CASES):
        raise ValueError("Audit lost a primary or repeat branch")
    _, refs = held_references(None, CASES)
    latest_resources = whole_iq.read(report / "resources.json")
    checks = []
    for case, branch in prior:
        raw_before = primary_resources[case][branch]
        raw_after = latest_resources[case][branch]
        equivalent = {
            k: raw_before[k] == raw_after[k]
            for k in ("raw_authority", "clock_sha256", "excluded_sha256", "probes_sha256")
            if k in raw_before and k in raw_after
        }
        hashes = {
            k: prior[case, branch][k] == recent[case, branch][k]
            for k in ("native_sha256", "input_sha256")
            if k in prior[case, branch] and k in recent[case, branch]
        }
        old_dir, new_dir = (base / case / branch for base in (primary, repeat_work))
        same_scientific_request = None
        if "input_sha256" in hashes:
            old_req, new_req = (
                whole_iq.read(
                    whole_iq.checked(folder / "recording/request.json", row["input_sha256"])
                )
                for folder, row in ((old_dir, prior[case, branch]), (new_dir, recent[case, branch]))
            )
            same_scientific_request = relocated_request_equal(old_req, new_req, old_dir, new_dir)
        original_result = prior[case, branch]["result"]
        current_result = recent[case, branch]["result"]
        compare_position = original_result["status"] == current_result["status"] == "ok"
        checks.append(
            dict(
                case=case,
                branch=branch,
                same_support=equivalent,
                product_equal=hashes,
                scientific_request_equal_after_local_relocation=same_scientific_request,
                published_position_arms_equal=(
                    original_result["arms"] == current_result["arms"] if compare_position else None
                ),
                primary_status=prior[case, branch]["result"]["status"],
                repeat_status=recent[case, branch]["result"]["status"],
            )
        )
    out = report / "primary-repeat-audit"
    out.mkdir(exist_ok=True)
    predictions = "positions.jsonl.gz"
    pack(out / predictions, primary_rows + present)
    csv_file(out / "capture-era-v5.csv", list(v5_rows(refs)))
    old_scores = iq_comparison_results.score_rows(
        primary_rows, primary_resources, refs, "scout-primary-audit"
    )
    csv_file(out / "primary-scores.csv", old_scores)
    save_json(out / "primary-resources.json", primary_resources)
    save_json(
        out / "primary-repeat-provenance.json",
        dict(
            primary_source_lock_sha256=PRIMARY_SHA,
            repeat_prediction_lock_sha256=_sha(report / "prediction-lock.json"),
            exporter_sha256=_sha(Path(__file__)),
            cases=receipts,
            paired_checks=checks,
        ),
    )
    names = (
        predictions,
        "capture-era-v5.csv",
        "primary-scores.csv",
        "primary-resources.json",
        "primary-repeat-provenance.json",
    )
    save_json(
        out / "audit-figure-lock.json",
        dict(
            cases=CASES,
            files={name: _sha(out / name) for name in names},
        ),
    )
    labels = (
        ("one", "Sixteen starts · secondary", "scout-deadline-repeat_candidate"),
        ("stock", "Four starts · secondary", "scout-deadline-repeat_control"),
        ("one_native_factors", "Sixteen starts · primary", "scout-primary-audit_candidate"),
        ("all_visits", "Four starts · primary", "scout-primary-audit_control"),
    )
    series = [
        dict(
            key=key,
            label=label,
            file=predictions,
            value=m,
            native_authority="frozen",
            native_field="paired_capture_sha256",
            match=["tile", "catalog_sha256", "original_request_sha256", "mode"],
        )
        for key, label, m in labels
    ]
    identifier = "scout-deadline-primary-audit"
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=identifier,
                    method=identifier,
                    scope="roof",
                    cases=CASES,
                    title="Primary timeout outcomes beside their two-case deadline repeat",
                    caption=(
                        "Audit of the two primary timeout cases and their fresh full-IQ repeats. "
                        "Both studies use the same memory, swap and 360 s limits. "
                        "The repeats use local ext4 scratch."
                    ),
                    seal="audit-figure-lock.json",
                    provenance=list(names[1:]),
                    series=series,
                )
            ],
        ),
    )
    figure_books.generate(
        out / "charts", ARMS, methods=[identifier], panel="screening", evidence=out
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--primary", default=PRIMARY, type=Path)
    cli.add_argument("--report", default=REPORT, type=Path)
    cli.add_argument("--repeat-work", required=True, type=Path)
    args = cli.parse_args()
    audit(args.primary, args.report, args.repeat_work.resolve())
