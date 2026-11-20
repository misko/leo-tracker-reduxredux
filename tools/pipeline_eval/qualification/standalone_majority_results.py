"""Score exact diagnosed standalone majority pairs against their sealed controls."""

import gzip

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km
from . import cavity_payload_transfer_results as parent
from . import screening_figures
from . import standalone_majority as trial
from .fresh_scenes import _read, _sha
from .native_joint_full_results import roi_margin
from .transfer_budget_results import sealed

POSITIONS = "figure-positions.jsonl.gz"
CUT = "initial_compatible_support_not_majority"


def same_science(a, b):
    def strip(r):
        return dict(
            r,
            metrics={
                k: v for k, v in r["metrics"].items() if k not in ("initial_support", "stage_s")
            },
        )

    return strip(a) == strip(b)


def validate_stage(row):
    result = row["result"]
    support = result["metrics"].get("initial_support")
    witnessed = {stage["name"] for stage in row["runtime"]["stage"]}
    if support is not None and (
        support["admitted"] != trial.frozen.admits_recovery(support)
        or "initial_support" not in witnessed
    ):
        raise ValueError("reported gate differs from the frozen majority or stage witness")
    if result.get("reason") == CUT and (
        support is None
        or support["admitted"]
        or "conservative_recovery" in witnessed
        or any(f.get("latlon") is not None for f in result["arms"].values())
    ):
        raise ValueError("a rejected input advanced or supplied a coordinate")
    return support


def summary(row):
    resource = (row["runtime"]["finish"] or [{}])[0]
    stages = row["result"]["metrics"].get("stage_s", {})
    return dict(
        status=row["result"]["status"],
        wall_s=row["wall_s"],
        cpu_s=resource.get("cgroup_cpu_s"),
        peak_bytes=resource.get("cgroup_peak"),
        initial_s=stages.get("initial"),
        conservative_s=stages.get("conservative"),
        gate_s=stages.get("initial_support"),
        after_initial_stage_s=sum(
            stages.get(name, 0.0) for name in ("conservative", "family", "signed", "cavity")
        ),
    )


def score(output):
    sealed(output)
    source = _read(output / "source-lock.json")
    authority = output / "scoring-targets.json"
    if _sha(authority) != source["targets_sha256"]:
        raise ValueError("scoring ECEF authority differs from its pre-run commitment")
    raw = _read(output / "predictions.json")
    plan = {(r["id"], r["method"]): r for r in _read(output / "requests.json")}
    observed = {(r["id"], r["method"]): r for r in raw}
    if (
        len(raw) != 6
        or len(plan) != 6
        or observed.keys() != plan.keys()
        or any(not all(observed[key][k] == v for k, v in row.items()) for key, row in plan.items())
    ):
        raise ValueError("diagnosed run differs from its pre-bound roster")
    if _sha(trial.portable.REPORT / "prediction-lock.json") != source["prior_primary_sha256"]:
        raise ValueError("earlier matching reduced outcomes changed")
    sealed(trial.portable.REPORT)
    baseline = {
        row["id"]: row
        for row in _read(trial.portable.REPORT / "predictions.json")
        if row["method"] == trial.OLD
    }
    baseline[trial.NEAR] = observed[trial.NEAR, trial.OLD]
    truth = _read(authority)
    if any(set(label) != set(trial.SCORE_FIELDS) for label in truth.values()):
        raise ValueError("scoring target does not match the committed coordinate schema")
    rows, cases, pairs, queries = [], [], [], []
    for ident, label in truth.items():
        actual = observed[ident, trial.METHOD]
        original = baseline[ident]
        tile = actual["tile"]
        if any(
            actual[key] != original[key]
            for key in (*parent.BINDINGS, "tile", "capture_id", "screen_center")
        ):
            raise ValueError("control or target uses a different scientific input")
        latlon = label["latlon"]
        if not np.array_equal(geodetic_to_ecef_km(*latlon, 0), label["ecef_km"]):
            raise ValueError("geodesic scorer and declared ECEF reference differ")
        cohort = actual["cohort"]
        margin = roi_margin(latlon, tile)
        condition = (
            "Archived near omission" if ident == trial.NEAR else parent.CONDITIONS[label["role"]]
        )
        queries.append(
            dict(
                id=ident,
                recording=actual["capture_id"],
                truth=latlon,
                condition=condition,
                cohort=cohort,
                bindings={k: actual[k] for k in parent.BINDINGS},
            )
        )
        evidence = validate_stage(actual)
        pairs.append(
            dict(
                id=ident,
                cohort=cohort,
                true_margin_km=margin,
                initial_support=evidence,
                science_equal=same_science(actual["result"], original["result"]),
                majority=summary(actual),
                ungated=summary(original),
                ungated_timing="same-core-live" if ident == trial.NEAR else "archived-same-input",
            )
        )
        for row in (actual, original):
            cases.append(dict(row, cohort=cohort))
            selected = row["result"]
            for arm in ARMS:
                point = selected["arms"].get(arm, {})
                fix = point.get("latlon")
                rows.append(
                    dict(
                        id=ident,
                        cohort=cohort,
                        latitude=latlon[0],
                        role=label["role"],
                        method=row["method"],
                        arm=arm,
                        true_margin_km=margin,
                        status=selected["status"],
                        reason=selected.get("reason"),
                        error_km=distance_km(fix, latlon),
                        rf_rms_hz=point.get("rf_rms_hz"),
                        frequency_score=selected["metrics"].get(f"{arm}_frequency_score"),
                        false_publication=margin < 0 and fix is not None,
                    )
                )
    save_json(output / "scores.json", dict(rows=rows, comparisons=pairs))
    write(output / POSITIONS, gzip.compress(b"".join(encoded(p) + b"\n" for p in cases), mtime=0))
    return queries


def figures(output, queries):
    charts = []
    proof = ("source-lock.json", "prediction-lock.json", "scoring-targets.json")
    for name, title in (
        ("primary", "Standalone initial majority on the four diagnosed transfer offers"),
        ("archived-near", "Standalone initial majority on one archived near omission"),
    ):
        scope = "diagnosed-primary" if name == "primary" else name
        cases = [
            {k: v for k, v in q.items() if k != "cohort"} for q in queries if q["cohort"] == scope
        ]
        qname, lock = f"{name}-queries.json", f"{name}-figure-lock.json"
        save_json(output / qname, dict(queries=cases))
        save_json(
            output / lock,
            dict(
                cases=[r["id"] for r in cases],
                files={p: _sha(output / p) for p in (*proof, POSITIONS, qname)},
            ),
        )
        control = "Sealed prior standalone" if name == "primary" else "Same-core ungated standalone"
        charts.append(
            dict(
                id=f"standalone-majority-{name}",
                method=trial.METHOD,
                scope="transfer",
                cases="sealed",
                title=title,
                caption="Previously examined native GLRT inputs with exact paired offers.",
                queries=qname,
                seal=lock,
                provenance=list(proof),
                series=[
                    dict(
                        key="candidate",
                        label="Standalone strict majority",
                        file=POSITIONS,
                        value=trial.METHOD,
                        where=dict(cohort=scope),
                    ),
                    dict(
                        key="stock",
                        label=control,
                        file=POSITIONS,
                        value=trial.OLD,
                        where=dict(cohort=scope),
                        match=list(parent.BINDINGS),
                    ),
                ],
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=charts))
    screening_figures.generate(output / "figures", evidence=output)


if __name__ == "__main__":
    figures(trial.REPORT, score(trial.REPORT))
