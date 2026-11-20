"""Score phase acquisition after sealing and render matched native-joint controls."""

from collections import Counter

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS, distribution
from . import phase_capture_trial as trial
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .native_joint_results import geodata
from .prefix_figures import csv_file


def main():
    output = trial.OUTPUT
    phase = trial.joint.phase
    lock = phase._read(output / "prediction-lock.json")
    trial.joint.secant_full._verify_files(output, lock["files"])
    jobs, current = trial.setup()
    if current != phase._read(output / "plan.json"):
        raise ValueError("Sealed predictions use a different source or request")
    rows = read_predictions(output / "positions.jsonl.gz")
    if tuple(rows) != tuple(lock["cases"]) or tuple(rows) != trial.IDS:
        raise ValueError("sealed prediction IDs differ")
    controls = {row["id"]: receipt for row, _, receipt in jobs}
    ref = {
        r["id"]: r for panel in ("ds26-common127", "roof16") for r in phase.corpus.references(panel)
    }
    truth_keys = ("input_sha256", "native_sha256", "catalog_sha256", "observation_sha256", "tile")
    cohorts = [{"id": i, "cohort": "diagnosis"} for i in trial.DEVELOPMENT]
    cohorts += [{"id": i, "cohort": "confirmation"} for i in trial.CONFIRMATION]
    cohorts += [{"id": i, "cohort": "omitted"} for i in trial.OMITTED]
    chart_rows = []
    scores, omitted = [], []
    for entry in cohorts:
        ident, cohort = entry["id"], entry["cohort"]
        row, baseline = rows[ident], controls[ident]
        if any(
            row.get(key) != baseline.get(key)
            for key in truth_keys
            if key != "observation_sha256" or row["result"]["status"] in ("ok", "withheld")
        ):
            raise ValueError(f"{ident} original control used different factors or Graph")
        truth = ref[row["recording"]]["truth"]
        tile_margin = roi_margin(truth, row["tile"])
        if cohort == "omitted":
            if tile_margin >= 0:
                raise ValueError("omitted tile contains GNSS point")
            omitted.append(
                dict(
                    id=ident,
                    recording=row["recording"],
                    truth=truth,
                    condition="Correct region omitted",
                    bindings={key: row[key] for key in truth_keys if key in row and key != "tile"},
                )
            )
        for value in (row, baseline):
            chart_rows.append(dict(value, study_cohort=cohort))
            for arm in ARMS:
                scores.append(
                    dict(
                        id=ident,
                        cohort=cohort,
                        method=value["method"],
                        arm=arm,
                        anchors=value["result"]["metrics"].get("captured_orbits", 0),
                        tile_margin_km=tile_margin,
                        **geodata(value, arm, truth),
                    )
                )
    controls_file = "control-positions.jsonl.gz"
    files = dict(lock["files"], **{controls_file: pack(output, controls_file, controls.values())})
    chart_file = "chart-positions.jsonl.gz"
    files[chart_file] = pack(output, chart_file, chart_rows)
    csv_file(output / "scores.csv", scores)
    files["scores.csv"] = phase.digest(output / "scores.csv")
    save_json(output / "omitted-queries.json", dict(queries=omitted))
    files["omitted-queries.json"] = phase.digest(output / "omitted-queries.json")
    groups = []
    for cohort, method, arm in sorted({(r["cohort"], r["method"], r["arm"]) for r in scores}):
        matched = [
            r for r in scores if (r["cohort"], r["method"], r["arm"]) == (cohort, method, arm)
        ]
        groups.append(
            dict(
                cohort=cohort,
                method=method,
                arm=arm,
                total=len(matched),
                status=dict(Counter(r["status"] for r in matched)),
                **{
                    key: distribution(r[key] for r in matched)
                    for key in (
                        "error_km",
                        "forced_error_km",
                        "conditional_rms_hz",
                        "worker_wall_s",
                        "worker_cpu_s",
                    )
                },
            )
        )
    save_json(output / "summary.json", dict(groups=groups, scores=scores))
    files["summary.json"] = phase.digest(output / "summary.json")
    charts = []
    for cohort in ("diagnosis", "confirmation", "omitted"):
        cases = [r["id"] for r in cohorts if r["cohort"] == cohort]
        transfer = cohort == "omitted"
        filename = cohort + "-figure-lock.json"
        spec = dict(
            id="phase_capture-" + cohort,
            method=trial.method.METHOD,
            scope="transfer" if transfer else "roof",
            seal=filename,
            title={
                "diagnosis": "Blind phase capture on diagnosed arcs",
                "confirmation": "Blind phase capture confirmation",
                "omitted": "Blind phase capture with the correct tile omitted",
            }[cohort],
            caption="Causal full regional phase bank with shared anonymous-track anchors "
            "and a separate downstream holdout.",
            cases=cases,
            series=[
                dict(
                    key="candidate" if transfer else "one",
                    label="Blind phase capture and joint fit",
                    file=chart_file,
                    value=trial.method.METHOD,
                    where=dict(study_cohort=cohort),
                ),
                dict(
                    key="stock",
                    label="Archived nominal native joint fit",
                    file=chart_file,
                    value=trial.joint.METHOD,
                    match=["input_sha256", "observation_sha256"],
                    where=dict(study_cohort=cohort),
                ),
            ],
        )
        if transfer:
            spec["queries"] = "omitted-queries.json"
        save_json(output / filename, dict(cases=cases, files=files))
        charts.append(spec)
    save_json(output / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    main()
