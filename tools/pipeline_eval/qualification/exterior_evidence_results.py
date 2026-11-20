"""Score exact smooth positions before and after the frozen exterior verdict."""

import argparse
import json
from collections import Counter
from math import cos, radians
from pathlib import Path

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, distribution, thresholds
from . import boundary_roof_results as edge
from . import exterior_evidence_trial as trial

phase = trial.phase
METHODS = (trial.METHOD, trial.clock.METHOD)
CONDITIONS = edge.CONDITIONS
GATE_FIELDS = (
    "support_status",
    "conditional_tile_mass_lower",
    "held_interior_hz",
    "held_exterior_hz",
    "held_log_gain",
    "worst_delete_orbit_held_gain",
    "max_delete_orbit_shift_km",
    "matched_orbits",
    "development_uncertainty_sigma_hz",
)


def labels(output, work, plan, scope):
    if scope == "reserve":
        path = work / "reserve-evaluator.json"
        if phase.digest(path) != plan["reserve_evaluator_sha256"]:
            raise ValueError("reserve evaluator differs from its prospective SHA")
        write(output / scope / "evaluator.json", path.read_bytes())
        return {r["id"]: r for r in phase._read(path)["labels"]}
    all_rows = {}
    for folder in trial.SOURCE_COHORTS:
        path = folder / "evaluator.json"
        lock = phase._read(folder / "prediction-lock.json")
        if phase.digest(path) != lock["evaluator_sha256"]:
            raise ValueError("historical edge condition was changed")
        all_rows.update({r["id"]: r for r in phase._read(path)["labels"]})
    return all_rows


def verified_rows(output, lock, true):
    series = {method: read_predictions(output / f"{method}.jsonl.gz") for method in METHODS}
    expected = set(lock["cases"])
    if set(true) != expected or any(set(rows) != expected for rows in series.values()):
        raise ValueError("unexpected verifier/evaluator roster")
    held = {}
    for ident, after in series[trial.METHOD].items():
        before = series[trial.clock.METHOD][ident]
        label = true[ident]
        if (
            any(
                before.get(k) != after.get(k)
                for k in (
                    "input_sha256",
                    "native_sha256",
                    "catalog_sha256",
                    "tile",
                    "observation_sha256",
                )
            )
            or before["input_sha256"] != label["input_sha256"]
            or before["tile"] != label["tile"]
        ):
            raise ValueError("smooth or exterior output used a different native request or Graph")
        original, changed = before["result"], after["result"]
        gate = after["exterior"]
        if gate["state"] == "accepted" and changed["arms"] != original["arms"]:
            raise ValueError("exterior gate changed a smooth numerical output")
        if hash_key := gate.get("held_arc_sha256"):
            recording = before["recording"]
            if held.setdefault(recording, hash_key) != hash_key:
                raise ValueError("same recording used different frozen held arcs across its offers")
    return series


def scored_rows(series, true):
    output = []
    for method, records in series.items():
        for ident, row in records.items():
            after = series[trial.METHOD][ident]
            label = true[ident]
            gate = after["exterior"]
            diagnostics = gate.get("gate") or {}
            lat, lon = row["tile"]["center"]
            site_lat, site_lon = label["truth"]
            gate_frame_margin = row["tile"]["width_km"] / 2 - max(
                abs((site_lat - lat) * 111.0),
                abs((site_lon - lon) * 111.32 * cos(radians(lat))),
            )
            for arm in ARMS:
                record = edge.shared.geodata(row, arm, label["truth"])
                output.append(
                    dict(
                        id=ident,
                        recording=row["recording"],
                        source_cohort=row["cohort"],
                        method=method,
                        arm=arm,
                        condition=label["condition"],
                        truth_margin_km=label["true_margin_km"],
                        gate_frame_truth_margin_km=gate_frame_margin,
                        exterior_state=gate["state"],
                        held_arc_sha256=gate.get("held_arc_sha256"),
                        exterior_wall_s=gate.get("worker_wall_s"),
                        exterior_cpu_s=gate.get("worker_cpu_s"),
                        exterior_peak_rss_kib=gate.get("peak_rss_kib"),
                        **{k: diagnostics.get(k) for k in GATE_FIELDS},
                        **record,
                    )
                )
    return output


def summarize(rows):
    result = []
    sources = ("all", *sorted({r["source_cohort"] for r in rows}))
    for cohort in sources:
        for arm in ARMS:
            group = [r for r in rows if r["arm"] == arm and cohort in ("all", r["source_cohort"])]
            original = {r["id"]: r for r in group if r["method"] == trial.clock.METHOD}
            for condition in CONDITIONS:
                after = [
                    r for r in group if r["method"] == trial.METHOD and r["condition"] == condition
                ]
                if not after:
                    continue
                before = [original[r["id"]] for r in after]
                tentative = [
                    r for r, base in zip(after, before, strict=True) if base["status"] == "ok"
                ]
                result.append(
                    dict(
                        source_cohort=cohort,
                        arm=arm,
                        condition=condition,
                        scheduled=len(after),
                        smooth_published=len(tentative),
                        gate_states=dict(Counter(r["exterior_state"] for r in tentative)),
                        smooth_statuses=dict(Counter(r["status"] for r in before)),
                        exterior_statuses=dict(Counter(r["status"] for r in after)),
                        original_error_km=distribution(r["error_km"] for r in before),
                        gated_error_km=distribution(r["error_km"] for r in after),
                        original_within_km=thresholds([r["error_km"] for r in before]),
                        gated_within_km=thresholds([r["error_km"] for r in after]),
                        smooth_conditional_rms_hz=distribution(
                            r["conditional_rms_hz"] for r in before
                        ),
                        gate_wall_s=distribution(r["exterior_wall_s"] for r in tentative),
                    )
                )
    return result


def publication_counts(rows):
    counts = {}
    for arm in ARMS:
        by_id = {(r["method"], r["id"]): r for r in rows if r["arm"] == arm}
        groups = {}
        for name, missing in (("present", False), ("omitted", True)):
            selection = [
                r
                for r in by_id.values()
                if r["method"] == trial.clock.METHOD and (r["truth_margin_km"] < 0) == missing
            ]
            attempted = [r for r in selection if r["status"] == "ok"]
            candidate = [by_id[trial.METHOD, r["id"]] for r in attempted]
            groups[name] = dict(
                scheduled=len(selection),
                recording_count=len({r["recording"] for r in selection}),
                original_published=len(attempted),
                gated_published=sum(r["status"] == "ok" for r in candidate),
                original_published_recordings=len({r["recording"] for r in attempted}),
                gated_published_recordings=len(
                    {r["recording"] for r in candidate if r["status"] == "ok"}
                ),
                states=dict(Counter(r["exterior_state"] for r in candidate)),
            )
        counts[arm] = groups
    return counts


def figure(output, scope, lock, series, true):
    files = dict(lock["files"])
    queries = []
    for ident in lock["cases"]:
        row = series[trial.METHOD][ident]
        label = true[ident]
        queries.append(
            dict(
                id=ident,
                condition=label["condition"],
                recording=label["recording"],
                truth=label["truth"],
                bindings={k: row[k] for k in ("input_sha256", "native_sha256", "catalog_sha256")},
            )
        )
    save_json(output / "figure-queries.json", dict(queries=queries))
    files["figure-queries.json"] = phase.digest(output / "figure-queries.json")
    candidate = f"{trial.METHOD}.jsonl.gz"
    if any(r["result"]["status"] == "missing" for r in series[trial.METHOD].values()):
        candidate = "plot-positions.jsonl.gz"
        rows = []
        for row in series[trial.METHOD].values():
            result = row["result"]
            if result["status"] == "missing":
                result = dict(
                    result,
                    arms={
                        arm: dict(value, forced_latlon=None)
                        for arm, value in result["arms"].items()
                    },
                )
            rows.append(dict(row, result=result))
        files[candidate] = edge.shared.pack(output, candidate, rows)
    save_json(output / "figure-lock.json", dict(cases=lock["cases"], files=files))
    chart = dict(
        id=f"native_smooth_exterior_evidence-{scope}",
        method=trial.METHOD,
        scope="transfer",
        title="Exterior held evidence on archival roof offers"
        if scope == "diagnostic-stress"
        else "Exterior held evidence on six reserved roof captures",
        caption="Frozen exterior rule with the matched native smooth publication pair."
        if scope == "diagnostic-stress"
        else "Four exterior checks completed. Five original-offer candidates remain unmeasured.",
        cases=lock["cases"],
        seal="figure-lock.json",
        queries="figure-queries.json",
        condition_labels=edge.LABELS
        if scope == "diagnostic-stress"
        else edge.LABELS
        | {
            "near-inside": "1.5 km inside",
            "near-outside": "1.5 km outside",
        },
        series=[
            dict(
                key="candidate",
                label="Exterior gate applied",
                file=candidate,
                value=trial.METHOD,
                forced_label="Gated smooth · forced",
            ),
            dict(
                key="stock",
                label="Native smooth",
                file=f"{trial.clock.METHOD}.jsonl.gz",
                value=trial.clock.METHOD,
                forced_label="Native smooth · forced",
                match=["input_sha256", "tile"],
            ),
        ],
    )
    if all(r.get("observation_sha256") for r in series[trial.clock.METHOD].values()):
        chart["series"][1]["match"].append("observation_sha256")
    write(
        output / "figures.json",
        json.dumps(dict(version=1, charts=[chart]), indent=2).encode() + b"\n",
    )


def score(output, work, scopes=("diagnostic-stress", "reserve")):
    for scope in scopes:
        dest = output / scope
        lock = phase._read(dest / "prediction-lock.json")
        trial.clock.base.secant_full._verify_files(dest, lock["files"])
        plan = output / "plan.json"
        if phase.digest(plan) != lock["plan_sha256"]:
            raise ValueError("frozen trial plan was changed after sealing predictions")
        truth = labels(output, work, phase._read(plan), scope)
        series = verified_rows(dest, lock, truth)
        rows = scored_rows(series, truth)
        edge.shared.csv_file(dest / "scores.csv", rows)
        gates = [r["exterior"] for r in series[trial.METHOD].values()]
        save_json(
            dest / "summary.json",
            dict(
                groups=summarize(rows),
                gate_states=lock["states"],
                publications=publication_counts(rows),
                elapsed_s=lock["elapsed_s"],
                resource={
                    k: distribution(r.get(k) for r in gates)
                    for k in ("worker_wall_s", "worker_cpu_s", "peak_rss_kib")
                },
                tile_frame_margin_max_difference_km=max(
                    abs(r["truth_margin_km"] - r["gate_frame_truth_margin_km"]) for r in rows
                ),
                tile_frame_membership_changes=sum(
                    (r["truth_margin_km"] < 0) != (r["gate_frame_truth_margin_km"] < 0)
                    for r in rows
                    if r["arm"] == "c0" and r["method"] == trial.METHOD
                ),
            ),
        )
        figure(dest, scope, lock, series, truth)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=trial.WORK)
    cli.add_argument("--output", type=Path, default=trial.REPORT)
    cli.add_argument("--scope", choices=("diagnostic-stress", "reserve"))
    args = cli.parse_args()
    score(args.output, args.work, (args.scope,)) if args.scope else score(args.output, args.work)


if __name__ == "__main__":
    main()
