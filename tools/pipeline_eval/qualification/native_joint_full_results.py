"""Seal and score full-roof native-joint predictions and genuine omitted controls."""

import argparse
from bisect import bisect_left
from collections import Counter
from pathlib import Path

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..__main__ import encoded, read_predictions, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from . import native_joint_full as trial
from .armijo_finish_results import pack
from .native_joint_results import geodata
from .prefix_figures import csv_file
from .secant_fit_trial import failed_result

base = trial.base
phase = base.phase
METHOD = base.METHOD
PREDICTIONS = "positions.jsonl.gz"
HISTOGRAMS = {
    "radius_km": (1, 2, 4, 6, 8, 12.5, 20),
    "pooled_shift_km": (0.25, 0.5, 1, 2, 4, 6, 12),
    "held_score": (0.1, 0.2, 0.28, 0.4, 0.6, 0.8, 1),
    "roi_margin_km": (0, 0.75, 1, 2, 4, 8, 12.5),
}
SUPPORT = (
    "orbit_count",
    "separated_orbits",
    "fit_tracks",
    "curved_fit_tracks",
    "held_tracks",
    "associated_observations",
    "pooled_shift_km",
    "repeated_orbits",
    "cross_radio_orbits",
    "paired_training_moves",
    "paired_full_moves",
)


def seal(work, bundle, output, *, prepare=trial.prepare, method=METHOD, fail=failed_result):
    plan = phase._read(work / "plan.json")
    if plan != prepare(bundle)[0]:
        raise ValueError("frozen full replay inputs or source changed")
    rows = []
    for query in plan["cases"]:
        ident = query["id"]
        packet = query["packet"]
        expected = dict(
            id=ident,
            recording=query["recording"],
            cohort=query["cohort"],
            method=method,
            input_sha256=phase.corpus._sha(encoded(packet)),
            native_sha256=packet["native"]["sha256"],
            catalog_sha256=packet["catalogue"]["sha256"],
            tile=packet["offer"],
        )
        path = work / "predictions" / f"{ident}.json"
        if not path.is_file():
            rows.append(
                dict(
                    expected,
                    result=fail("missing", "not completed before batch deadline"),
                    worker_wall_s=None,
                )
            )
            continue
        row = phase._read(path)
        if row.get("cpu") not in plan["cpus"] or any(row.get(k) != v for k, v in expected.items()):
            raise ValueError(f"{ident} worker returned a different input or method")
        validate_result(row["result"])
        if row["result"]["status"] in ("ok", "withheld") and (
            not row.get("observation_sha256")
            or row.get("address_space_limit_mib") != 512
            or row["proc_memory_kib"]["VmPeak"] > 512 * 1024
            or any(
                "localization_v3" in path or "/v5_" in path for path in row["imported_first_party"]
            )
        ):
            raise ValueError(f"{ident} worker violates the frozen native/memory boundary")
        rows.append(row)
    save_json(output / "plan.json", plan)
    files = {
        PREDICTIONS: pack(output, PREDICTIONS, rows),
        "plan.json": phase.digest(output / "plan.json"),
    }
    receipt = work / "run-receipt.json"
    run = phase._read(receipt) if receipt.is_file() else None
    if run:
        counts = Counter(r["result"]["status"] for r in rows if r["result"]["status"] != "missing")
        if run["wall_s"] > plan["wall_cap_s"] or (
            run["scheduled"],
            run["attempted"],
            run["statuses"],
        ) != (len(rows), counts.total(), dict(counts)):
            raise ValueError("full replay differs from its run receipt or time budget")
    save_json(
        output / "prediction-lock.json",
        dict(cases=[row["id"] for row in rows], files=files, run=run),
    )


def roi_margin(point, tile):
    """Signed distance to the closest edge in the offer's tangent coordinates."""
    if point is None:
        return None
    origin = geodetic_to_ecef_km(*tile["center"], 0)
    frame = ecef_to_enu_matrix(*tile["center"])
    displacement = geodetic_to_ecef_km(*point, 0) - origin
    up = ecef_to_enu_matrix(*point)[2]
    facing = frame[2] @ up
    if facing <= 0:
        raise ValueError("point is beyond the extent of the regional tangent projection")
    tangent = displacement - up * ((frame[2] @ displacement) / facing)
    margin = float(tile.get("width_km", 25.0) / 2 - max(abs(frame[:2] @ tangent)))
    return 0.0 if abs(margin) < 1e-8 else margin


def histogram(values, upper_edges):
    bins = [0] * (len(upper_edges) + 1)
    unavailable = 0
    for value in values:
        if value is None:
            unavailable += 1
        else:
            bins[bisect_left(upper_edges, value)] += 1
    return dict(inclusive_upper_edges=list(upper_edges), counts=bins, unavailable=unavailable)


def original_scores(ident, ref, bindings, truth):
    directory = (phase.ARCHIVE if ident.startswith("DS26-") else phase.DS29) / f"{ident}-r0"
    result = {}
    for role in ROLES:
        entry = directory / f"{role}-execution.json"
        if phase.digest(entry) != bindings[role]["execution_sha256"]:
            raise ValueError(
                f"{ident} {role} execution differs from the exact native/catalogue seal"
            )
        result[role] = {}
        execution = phase._read(entry)
        if execution["request_sha256"] != bindings[role]["request_sha256"]:
            raise ValueError(f"{ident} {role} execution does not match the frozen request")
        for arm, endpoint in execution["worker"]["arms"].items():
            point = endpoint["endpoint_latlon"]
            if (
                delta := distance_km(point, ref["reference"][role][arm]["latlon"])
            ) is None or delta > 1e-6:
                raise ValueError(f"{ident} {role} output differs from the official frozen score")
            result[role][arm] = distance_km(point, truth), endpoint.get("residual_rms_hz")
    return result


def summarize(rows):
    output = []
    for cohort in ("roof", "omitted"):
        for dataset in ("all", "DS26", "DS29"):
            for arm in ARMS:
                group = [
                    r
                    for r in rows
                    if r["cohort"] == cohort
                    and r["arm"] == arm
                    and dataset in ("all", r["dataset"])
                ]
                if not group:
                    continue
                errors = [r["error_km"] for r in group]
                detail = dict(
                    cohort=cohort,
                    dataset=dataset,
                    arm=arm,
                    scheduled=len(group),
                    statuses=dict(Counter(r["status"] for r in group)),
                    withheld_reasons=dict(
                        Counter(r["reason"] for r in group if r["status"] == "withheld")
                    ),
                    within_km=thresholds(errors),
                    distributions={
                        name: distribution(r[name] for r in group)
                        for name in (
                            "error_km",
                            "forced_error_km",
                            "conditional_rms_hz",
                            "objective",
                            "held_score",
                            "held_orbits",
                            "held_normalized_mean_loss",
                            "radius_km",
                            "roi_margin_km",
                            *SUPPORT,
                            "fitted_c_hz_per_ghz",
                            "worker_wall_s",
                            "worker_cpu_s",
                            "peak_rss_kib",
                            "vm_peak_kib",
                            "graph_wall_s",
                            "joint_solver_wall_s",
                        )
                    },
                    histograms={
                        label: {
                            name: histogram(
                                (r[name] for r in group if label == "all" or r["status"] == label),
                                edges,
                            )
                            for name, edges in HISTOGRAMS.items()
                        }
                        for label in ("all", "ok", "withheld")
                    },
                )
                if cohort == "roof":
                    detail["original_options"] = {
                        role: dict(
                            scheduled=len(group),
                            error_km=distribution(r[f"{role}_error_km"] for r in group),
                            original_report_rms_hz=distribution(r[f"{role}_rms_hz"] for r in group),
                            on_joint_published_error_km=distribution(
                                r[f"{role}_error_km"] for r in group if r["error_km"] is not None
                            ),
                            within_km=thresholds([r[f"{role}_error_km"] for r in group]),
                            **phase._pair_summary(
                                [
                                    (r["error_km"], r[f"{role}_error_km"])
                                    for r in group
                                    if r["error_km"] is not None
                                ]
                            ),
                        )
                        for role in ROLES
                    }
                output.append(detail)
    return output


def ablation(rows):
    summaries = {}
    zero = {r["id"]: r for r in rows if r["arm"] == "c0"}
    calibrated = {r["id"]: r for r in rows if r["arm"] == "fitted_c"}
    for dataset in ("all", "DS26", "DS29"):
        pairs = [
            (r, calibrated[key])
            for key, r in zero.items()
            if r["cohort"] == "roof" and dataset in ("all", r["dataset"])
        ]
        summaries[dataset] = {
            name: dict(
                n=len(deltas),
                decreased=sum(d < 0 for d in deltas),
                increased=sum(d > 0 for d in deltas),
                fitted_minus_zero=distribution(deltas),
            )
            for name in ("error_km", "forced_error_km", "conditional_rms_hz", "held_score")
            if (
                deltas := [
                    b[name] - a[name]
                    for a, b in pairs
                    if a[name] is not None and b[name] is not None
                ]
            )
        }
    return summaries


def repeatability(predictions):
    prior_lock = phase._read(base.REPORT / "prediction-lock.json")
    base.secant_full._verify_files(base.REPORT, prior_lock["files"])
    prior = read_predictions(base.REPORT / PREDICTIONS)
    fields = ("input_sha256", "native_sha256", "catalog_sha256", "observation_sha256", "tile")
    repeats = {}
    for ident, archived in prior.items():
        current = predictions[ident]
        switches = ("status", "reason", "arms")
        repeats[ident] = dict(
            exact_inputs=all(current.get(k) == archived.get(k) for k in fields),
            exact_decision_and_arms=all(
                current["result"].get(k) == archived["result"].get(k) for k in switches
            ),
        )
    return dict(prior_prediction_sha256=prior_lock["files"][PREDICTIONS], queries=repeats)


def matched_score_rows(predictions, plan, *, solver_stage="joint_backend"):
    controls = base.secant_full.REPORT / "receipt.json"
    if plan["compact_reference_receipt_sha256"] != phase.digest(controls):
        raise ValueError("original reference authority differs from the preregistered source")
    base.secant_full._verify_files(controls.parent, phase._read(controls)["files"])
    originals = phase._read(controls.parent / "original-v5-inputs.json")
    refs = {
        r["id"]: r for panel in ("ds26-common127", "roof16") for r in phase.corpus.references(panel)
    }
    rows, queries = [], []
    for record in predictions.values():
        ref = refs[record["recording"]]
        truth, cohort = ref["truth"], record["cohort"]
        metrics = record["result"]["metrics"]
        bindings = {k: record[k] for k in ("native_sha256", "catalog_sha256", "input_sha256")}
        margin = roi_margin(truth, record["tile"])
        if cohort == "omitted":
            if margin >= 0:
                raise ValueError(f"{record['id']} alternate tile contains the true point")
            queries.append(
                dict(
                    id=record["id"],
                    recording=record["recording"],
                    condition="Correct region omitted",
                    truth=truth,
                    bindings=bindings,
                )
            )
        else:
            original = original_scores(record["id"], ref, originals[record["id"]], truth)
        for arm in ARMS:
            point = record["result"]["arms"][arm]
            r = dict(
                id=record["id"],
                recording=record["recording"],
                dataset=ref["group"],
                cohort=cohort,
                arm=arm,
                true_tile_margin_km=margin,
                roi_margin_km=roi_margin(point.get("forced_latlon"), record["tile"]),
                radius_km=point.get("radius_km"),
                held_normalized_mean_loss=point.get("held_normalized_mean_loss"),
                **geodata(record, arm, truth),
                graph_wall_s=record.get("stages", {}).get("graph", {}).get("wall_s"),
                joint_solver_wall_s=record.get("stages", {}).get(solver_stage, {}).get("wall_s"),
                **{name: metrics.get(name) for name in SUPPORT},
            )
            for role in ROLES:
                e, v = original[role][arm] if cohort == "roof" else (None, None)
                r[f"{role}_error_km"], r[f"{role}_rms_hz"] = e, v
            rows.append(r)
    return rows, queries


def score(output):
    lock = phase._read(output / "prediction-lock.json")
    base.secant_full._verify_files(output, lock["files"])
    plan = phase._read(output / "plan.json")
    predictions = read_predictions(output / PREDICTIONS)
    if set(predictions) != set(lock["cases"]):
        raise ValueError("unexpected prediction roster")
    rows, queries = matched_score_rows(predictions, plan)
    csv_file(output / "scores.csv", rows)
    save_json(
        output / "summary.json",
        dict(
            groups=summarize(rows),
            c_ablation=ablation(rows),
            replay=lock["run"],
            repeatability_of_initial_nine=repeatability(predictions),
        ),
    )
    figures(output, predictions, queries, lock)


def figures(output, predictions, queries, lock):
    charts = []
    for cohort in ("roof", "omitted"):
        omitted = cohort == "omitted"
        cases = [i for i, r in predictions.items() if r["cohort"] == cohort]
        files = dict(lock["files"])
        spec = dict(
            id=f"native_joint_full-{cohort}",
            method=METHOD,
            scope="transfer" if omitted else "roof",
            title="Full native joint orbit replay"
            if not omitted
            else "Native joint with nine omitted tiles",
            caption="Complete native factors, one supplied tile, and a 512 MiB address-space cap.",
            cases=cases,
            seal=f"{cohort}-figure-lock.json",
            series=[
                dict(
                    key="candidate" if omitted else "one",
                    label="Streaming native joint orbit fit",
                    file=PREDICTIONS,
                    value=METHOD,
                    where=dict(cohort=cohort),
                )
            ],
        )
        if omitted:
            spec["queries"] = "omitted-queries.json"
            save_json(output / spec["queries"], dict(queries=queries))
            files[spec["queries"]] = phase.digest(output / spec["queries"])
        save_json(output / spec["seal"], dict(cases=cases, files=files))
        charts.append(spec)
    save_json(output / "figures.json", dict(version=1, charts=charts))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=trial.WORK)
    cli.add_argument("--bundle", type=Path, default=base.BUNDLE)
    cli.add_argument("--output", type=Path, default=trial.REPORT)
    args = cli.parse_args()
    seal(args.work, args.bundle, args.output)
    score(args.output)


if __name__ == "__main__":
    main()
