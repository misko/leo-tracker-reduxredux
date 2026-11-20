"""Seal selective-capture recorded controls, cost model, and paired calibration scores."""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import selective_capture_trial as trial
from .full_held_scores import held_references
from .input_factor_bridge import _sha, check, read
from .prefix_figures import csv_file

ORIGINAL = trial.SCREEN / "next/input-factor-comparison"
LINEAGE = trial.SCREEN / "detector-origins/lineage"
CERTIFICATE = trial.SCREEN / "detector-origins/pressure/candidate-lock.json"
SAME_SOLVER = "Recorded compact cavity control, with the same exact phase-release mathematics"
REPORT = trial.REPORT
ROLES = (*trial.METHODS, "wide", "capture")


def read_rows(path):
    with gzip.open(path, "rt") as stream:
        return [json.loads(row) for row in stream]


def member(folder, name):
    path = folder / name
    check(path, read(folder / "prediction-lock.json")["files"][name])
    return path


def control_rows(plan):
    by_role = {}
    sources = {
        "wide": (trial.BAND, "regional_wide_full_iq"),
        "capture": (ORIGINAL, "v5_secant_fit"),
    }
    for role, (folder, method) in sources.items():
        path = member(folder, "positions.jsonl.gz")
        archived = {r["id"]: r for r in read_rows(path) if r["method"] == method}
        for case in trial.CASES:
            key = plan["jobs"][case][trial.METHODS[0]]["row"]
            row = archived[case]
            native = key["wide_native_sha256" if role == "wide" else "original_native_sha256"]
            if (
                row["native_sha256"] != native
                or row["catalog_sha256"] != key["catalog_sha256"]
                or row.get("original_request_sha256", row.get("frozen_request_sha256"))
                != key["frozen_request_sha256"]
                or row["tile"] != {k: v for k, v in key["tile"].items() if k != "width_km"}
            ):
                raise ValueError(f"{case} {role} archival control differs from the frozen offer")
            by_role[(case, role)] = dict(
                row,
                method=f"selective_capture_{role}",
                original_native_sha256=key["original_native_sha256"],
                wide_native_sha256=key["wide_native_sha256"],
                frozen_request_sha256=key["frozen_request_sha256"],
                historical_control=True,
                archive_receipt_sha256=_sha(path),
                control_solver_boundary=SAME_SOLVER,
                cohort=key["cohort"],
            )
    return by_role


def estimates(plan):
    known = read(member(trial.BAND, "resources.json"))
    lineage_lock = read(LINEAGE / "source-lock.json")["files"]
    selection = read(REPORT / "selection-lock.json")
    costs = {}
    for case in trial.CASES:
        raw = LINEAGE / f"{case}.json.gz"
        check(raw, lineage_lock[raw.name])
        data = json.loads(gzip.decompress(raw.read_bytes()))
        original = [call["cpu_ms"] for row in data["rows"] for call in row["timings"]["capture"]]
        wide = known[case]["wide"]["detector_call_cpu_ms"]
        admitted = selection["cases"][case]["selection"]["admitted"]
        if wide["n"] != admitted:
            raise ValueError("wide measured raw-cost denominator differs from science inputs")
        overhead = selection["cases"][case]["selector_cpu_ms"] / admitted
        witness_path = REPORT / f"{case}-waveform.json"
        selected = read(witness_path) if witness_path.is_file() else {}
        witness = (
            selected["clocks"]["capture"]["cpu_ms"] if selected.get("status") == "ok" else None
        )
        role = {}
        for method in trial.METHODS:
            fraction = plan["jobs"][case][method]["row"]["selection"]["fraction"]
            cost = wide["mean"] + overhead + fraction * mean(original)
            role[method] = dict(
                fraction=fraction,
                estimated_mean_cpu_ms=cost,
                estimated_total_detector_cpu_s=cost * admitted / 1000,
                selected_witness_mean_sensitivity_ms=None
                if witness is None
                else wide["mean"] + overhead + fraction * witness,
            )
        costs[case] = dict(
            admitted=admitted,
            measured_full_wide_mean_cpu_ms=wide["mean"],
            measured_lineage_capture_mean_cpu_ms=mean(original),
            measured_lineage_capture_calls=len(original),
            observed_selector_ms_per_visit=overhead,
            selected_witness_capture_cpu_ms=witness,
            policies=role,
        )
    return costs


def publish(work, *, allow_partial):
    pins = trial.verify_selection(work)
    plan = read(REPORT / "fit-plan.json")
    check(REPORT / "selection-lock.json", plan["selection_sha256"])
    if not allow_partial and any(
        not (work / f"{c}-{m}-fit.json").is_file() for c in trial.CASES for m in trial.METHODS
    ):
        raise ValueError("one or more scheduled fit attempts are still in progress")
    controls = control_rows(plan)
    predictions, receipts = [], {}
    for case in trial.CASES:
        receipts[case] = {}
        for role in trial.METHODS:
            planned = plan["jobs"][case][role]["row"]
            attempt = work / f"{case}-{role}-fit.json"
            if attempt.is_file():
                measured = read(attempt)
                if any(measured[k] != v for k, v in planned.items()):
                    raise ValueError("completed fit has different frozen input metadata")
                if measured["result"]["status"] in ("ok", "withheld"):
                    proof = measured["runtime"]["proof"][0]
                    finish = measured["runtime"]["finish"][0]
                    if (
                        proof["memory"] != plan["memory_max"]
                        or proof["swap"] != plan["swap_max"]
                        or finish["cgroup_peak"] > plan["memory_max"]
                        or proof["cpu"] != measured["cpu"]
                        or case not in trial.LANES[proof["cpu"]]
                    ):
                        raise ValueError("completed fit lacks its declared memory/CPU custody")
                receipts[case][role] = measured
                result = measured["result"]
            else:
                result = dict(
                    status="missing",
                    reason="scheduled service had no terminal receipt",
                    boundary=trial.BOUNDARY,
                    metrics=dict(position_attempted=False),
                    arms={arm: {"latlon": None} for arm in ARMS},
                )
                receipts[case][role] = dict(planned, result=result)
            validate_result(result)
            predictions.append(
                dict(
                    planned,
                    method=f"selective_capture_{role}",
                    result=result,
                    tile={k: v for k, v in planned["tile"].items() if k != "width_km"},
                )
            )
        predictions.extend(controls[(case, role)] for role in ("wide", "capture"))
        if any(
            r["original_native_sha256"] != trial._load_case(case)["native"]["sha256"]
            for r in predictions
            if r["id"] == case
        ):
            raise ValueError("prediction lost its original factor provenance")
    costs = estimates(plan)
    prediction = REPORT / "positions.jsonl.gz"
    write(prediction, gzip.compress(b"".join(encoded(row) + b"\n" for row in predictions), mtime=0))
    save_json(REPORT / "fit-receipts.json", receipts)
    save_json(REPORT / "detector-cost.json", costs)
    files = [
        "PROTOCOL.md",
        "selection-lock.json",
        "fit-plan.json",
        "fit-receipts.json",
        "detector-cost.json",
        prediction.name,
        "figures.json",
    ]
    files.extend(
        f"{c}-waveform.json" for c in trial.CASES if (REPORT / f"{c}-waveform.json").exists()
    )
    if (REPORT / "waveform-plan.json").exists():
        files.append("waveform-plan.json")
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(trial.CASES),
            files={n: _sha(REPORT / n) for n in files},
            sources={str(CERTIFICATE): _sha(CERTIFICATE)},
            eligible_visits={c: pins["cases"][c]["selection"]["admitted"] for c in trial.CASES},
        ),
    )


def score():
    path = member(REPORT, "positions.jsonl.gz")
    refs = {d["id"]: d for d in held_references(None, trial.CASES)[1]}
    rows, overview = [], defaultdict(list)
    for row in read_rows(path):
        reference = refs[row["id"]]
        for arm in ARMS:
            arm_values = row["result"].get("arms", {}).get(arm, {})
            error = distance_km(arm_values.get("latlon"), reference["truth"])
            v5 = reference["reference"]["baseline"][arm]["error_km"]
            status = row["result"]["status"]
            result = dict(
                id=row["id"],
                method=row["method"],
                cohort=row["cohort"],
                arm=arm,
                status=status,
                error_km=error,
                conditional_rf_rms_hz=arm_values.get("rf_rms_hz"),
                original_v5_error_km=v5,
                within_5_pct=error is not None and error <= 1.05 * v5,
                within_10_pct=error is not None and error <= 1.10 * v5,
            )
            rows.append(result)
            overview[(row["method"], arm)].append(result)
    csv_file(REPORT / "scores.csv", rows)
    totals = {}
    for (method, arm), data in overview.items():
        cohort = totals.setdefault(method, {})
        errors = [r["error_km"] for r in data if r["error_km"] is not None]
        cohort[arm] = dict(
            attempts=len(data),
            fixes=len(errors),
            median_error_km=median(errors) if errors else None,
            within_5_pct=sum(r["within_5_pct"] for r in data),
            within_10_pct=sum(r["within_10_pct"] for r in data),
        )
    save_json(REPORT / "summary.json", totals)
    save_json(
        REPORT / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(REPORT / "prediction-lock.json"),
            files={n: _sha(REPORT / n) for n in ("scores.csv", "summary.json")},
            exporter_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("work", type=local_output)
    cli.add_argument("--allow-partial", action="store_true")
    args = cli.parse_args()
    publish(args.work, allow_partial=args.allow_partial)
    score()
