"""Seal the six paced position outcomes, then score and render both calibration arms."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import adaptive_arrival_position as trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .screening_figures import generate
from .whole_pressure_trial import rows_from

POSITION = "paced-positions.jsonl.gz"
PREDICTION = "position-prediction-lock.json"
SCORE = "position-scores.csv"
FIGURE_LOCK = "position-figure-lock.json"


def absent_position(ident, mode, launch_sha):
    case, _ = whole_iq.binding(ident)
    return dict(
        id=ident,
        method=trial.METHOD[mode],
        paced_mode=mode,
        mode="matched-tile",
        cpu=trial.CPU[ident],
        tile=case["regions"][0],
        catalog_sha256=case["catalog"]["sha256"],
        original_request_sha256=case["request"]["sha256"],
        paired_capture_sha256=case["native"]["sha256"],
        native_sha256=None,
        trace_sha256=None,
        counts=None,
        raw_verified=False,
        raw_status="absent",
        position_source_sha256=launch_sha,
        origin="terminal paced position evidence absent at the declared publication cutoff",
        resources={},
        result=trial.empty_result("unavailable", "position_evidence_absent_at_cutoff"),
    )


def freeze_predictions(report, allow_absent=False):
    dest = report / PREDICTION
    if dest.is_file():
        seal = whole_iq.read(dest)
        trial.checked_member(report, POSITION, seal["files"])
        return
    launch = report / "position-source-lock.json"
    launch_sha = _sha(launch)
    planned = whole_iq.read(launch)
    if (
        planned["candidate_cpu"] != trial.CPU
        or planned["prior_arrival_source_sha256"] != trial.QUEUE_PIN
    ):
        raise ValueError("frozen numerical roster no longer matches the experiment")
    rows, absent = [], []
    evidence = {launch.name: launch_sha}
    for ident in trial.CPU:
        for mode in trial.METHOD:
            prefix = f"{ident}-{mode}-position"
            path = report / f"{prefix}-lock.json"
            if not path.is_file():
                if not allow_absent:
                    raise FileNotFoundError(f"unsealed paced position {ident}/{mode}")
                absent.append([ident, mode])
                rows.append(absent_position(ident, mode, launch_sha))
                continue
            lock = whole_iq.read(path)
            if (lock["cases"], lock["mode"]) != ([ident], mode):
                raise ValueError("position lock belongs to another recording or mode")
            evidence[path.name] = _sha(path)
            for name, digest in lock["files"].items():
                trial.checked_member(report, name, lock["files"])
                evidence[name] = digest
            (row,) = rows_from(report / f"{prefix}.jsonl.gz")
            if (
                (row["id"], row["method"], row["paced_mode"]) != (ident, trial.METHOD[mode], mode)
                or row["raw_lock_sha256"] != lock["raw_lock_sha256"]
                or row["position_source_sha256"] != launch_sha
            ):
                raise ValueError("a paced position moved outside its sealed input/branch")
            source = report / row["raw_lock"]
            whole_iq.checked(source, row["raw_lock_sha256"])
            evidence[source.name] = row["raw_lock_sha256"]
            raw, _, trace = trial.raw_attempt(report, ident, mode)
            if _sha(trace) != row["trace_sha256"] or row["raw_verified"] != raw["raw_verified"]:
                raise ValueError("position receipt does not reference its genuine paced trace")
            validate_result(row["result"])
            rows.append(row)
    pack(report / POSITION, rows)
    evidence[POSITION] = _sha(report / POSITION)
    save_json(
        dest,
        dict(
            cases=list(trial.CPU),
            modes=list(trial.METHOD),
            absent=absent,
            files=evidence,
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def arm_score(row, ref, arm):
    result = row["result"]
    measured = result.get("arms", {}).get(arm, {})
    position = measured.get("latlon")
    lat, lon = position if position is not None else (None, None)
    error = distance_km(position, ref["truth"])
    original = ref["reference"]["baseline"][arm]["error_km"]
    counts = row["counts"] or {}
    resources = row["resources"]
    return dict(
        id=row["id"],
        paced_mode=row["paced_mode"],
        method=row["method"],
        arm=arm,
        raw_status=row["raw_status"],
        position_status=result["status"],
        reason=result.get("reason"),
        origin=row["origin"],
        scheduled_visits=counts.get("recorded"),
        emitted=counts.get("emitted"),
        queue_drops=counts.get("queue_drop"),
        invalid_captures=counts.get("invalid_capture"),
        emitted_stock=counts.get("stock"),
        emitted_fifth=counts.get("fifth"),
        native_sha256=row["native_sha256"],
        latitude=lat,
        longitude=lon,
        error_km=error,
        within_10pct=(error is not None and original is not None and error <= 1.10 * original),
        conditional_rf_rms_hz=measured.get("rf_rms_hz"),
        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
        solver_observations=result["metrics"].get("observations"),
        solver_tracks=result["metrics"].get("tracks"),
        solver_cpu_s=resources.get("cpu_s"),
        solver_wall_s=resources.get("wall_s"),
        solver_peak_bytes=resources.get("peak_bytes"),
    )


def history(references):
    records = []
    for ident, ref in references.items():
        case, _ = whole_iq.binding(ident)
        for role in ROLES:
            for arm in ARMS:
                position = ref["reference"][role][arm]
                records.append(
                    dict(
                        id=ident,
                        role=role,
                        arm=arm,
                        status=position["status"],
                        input_native_sha256=case["native"]["sha256"],
                        latitude=(position.get("latlon") or [None, None])[0],
                        longitude=(position.get("latlon") or [None, None])[1],
                        error_km=position.get("error_km"),
                        published_rf_rms_hz=position.get("rf_rms_hz"),
                        archived_wall_s=position.get("wall_s"),
                    )
                )
    return records


def panels(report, cases):
    provenance = (
        PREDICTION,
        "position-source-lock.json",
        SCORE,
        "position-summary.json",
        "position-v5-controls.csv",
    )
    save_json(
        report / FIGURE_LOCK,
        dict(cases=cases, files={name: _sha(report / name) for name in (POSITION, *provenance)}),
    )

    def series(key, mode, label):
        return dict(
            key=key,
            file=POSITION,
            value=trial.METHOD[mode],
            label=label,
            native_field="paired_capture_sha256",
            match=["tile", "catalog_sha256", "original_request_sha256", "position_source_sha256"],
        )

    save_json(
        report / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="adaptive-arrival-position",
                    method=trial.METHOD["adaptive"],
                    scope="roof",
                    cases="sealed",
                    seal=FIGURE_LOCK,
                    provenance=provenance,
                    title="Position after measured queue-triggered detection",
                    caption=(
                        "Paced stock, fifth-center and adaptive emissions feed identical geometry. "
                        "Both calibration arms are measured. Original v5 uses capture-era factors."
                    ),
                    series=[
                        series("one", "adaptive", "Queue-triggered fifth center"),
                        series("stock", "stock", "Paced stock wide"),
                        series("one_native_factors", "fifth", "Paced fifth center"),
                    ],
                )
            ],
        ),
    )
    generate(report / "position-charts", evidence=report)


def score(report, allow_absent=False):
    freeze_predictions(report, allow_absent)
    receipt = whole_iq.read(report / PREDICTION)
    for name, digest in receipt["files"].items():
        whole_iq.checked(report / name, digest)
    rows = rows_from(report / POSITION)
    _, authority = held_references("roof16", trial.CPU)
    refs = {row["id"]: row for row in authority}
    scores = [arm_score(row, refs[row["id"]], arm) for row in rows for arm in ARMS]
    csv_file(report / SCORE, scores)
    csv_file(report / "position-v5-controls.csv", history(refs))
    summary = {}
    for mode in trial.METHOD:
        summary[mode] = {}
        for arm in ARMS:
            use = [r for r in scores if (r["paced_mode"], r["arm"]) == (mode, arm)]
            summary[mode][arm] = dict(
                scheduled=len(use),
                published=sum(r["error_km"] is not None for r in use),
                within_10pct=sum(r["within_10pct"] for r in use),
                state={r["id"]: r["position_status"] for r in use},
            )
    save_json(report / "position-summary.json", summary)
    panels(report, receipt["cases"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    parser.add_argument("--allow-absent-at-cutoff", action="store_true")
    args = parser.parse_args()
    score(args.report, args.allow_absent_at_cutoff)
