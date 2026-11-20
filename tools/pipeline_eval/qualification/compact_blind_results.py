"""Score sealed compact position replays after the blind predictors are terminal."""

import argparse
import csv
import gzip
import io
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from ..__main__ import save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import compact_blind_generator as generator
from . import compact_blind_trial as trial
from . import screening_figures as standard
from .armijo_finish_results import pack

CONDITIONS = ("containing", "omitted")
REFERENCE = "v5_original_regional_reference"


def load_predictions(out, expected):
    with gzip.open(out / "positions.jsonl.gz", "rt") as archive:
        rows = list(map(json.loads, archive))
    key = {(r["id"], r["method"]) for r in rows}
    if len(key) != len(rows) or key != {(i, m) for i in expected for m in trial.METHODS}:
        raise ValueError("sealed position archive does not contain all planned profile/query pairs")
    return rows


def row_score(row, case, target, arm):
    result, condition = row["result"], target["condition"]
    endpoint = result["arms"][arm]
    coord = endpoint["latlon"]
    truth = target["site"]
    launcher_only = row["method"] in trial.METHODS
    stage_wall = result.get("metrics", {}).get("stage_s", {}) if launcher_only else {}
    return dict(
        id=row["id"],
        session=case["session"],
        method=row["method"],
        condition=condition,
        arm=arm,
        status=result["status"],
        reason=result.get("reason"),
        published=coord is not None,
        false_publication=condition == "omitted" and coord is not None,
        geographic_error_km=distance_km(truth, coord),
        forced_error_km=distance_km(truth, endpoint.get("forced_latlon")),
        offer_center_error_km=distance_km(truth, case["tile"]),
        published_inside_offer=None
        if coord is None
        else (max(map(abs, generator.local_offset(coord, case["tile"]))) <= 12.5 + 1e-9),
        rf_rms_hz=endpoint.get("rf_rms_hz"),
        native_sha256=row["native_sha256"],
        input_sha256=row["input_sha256"],
        catalogue_sha256=row["catalogue_sha256"],
        wall_s=row["worker_wall_s"],
        native_preparation_wall_s=stage_wall.get("native_preparation"),
        numerical_stages_wall_s=sum(stage_wall.values()) if stage_wall else None,
        cpu_s=None if launcher_only else row.get("worker_cpu_s"),
        rss_kib=None if launcher_only else row.get("peak_rss_kib"),
    )


def cohort(rows, method, condition, arm):
    subset = [
        r for r in rows if (r["method"], r["condition"], r["arm"]) == (method, condition, arm)
    ]
    if len(subset) != 4:
        raise ValueError("the frozen denominator requires four independent simulated sites")
    return dict(
        attempts=len(subset),
        published=sum(r["published"] for r in subset),
        false_publications=sum(r["false_publication"] for r in subset),
        published_within_5km=sum(
            r["geographic_error_km"] is not None and r["geographic_error_km"] <= 5 for r in subset
        ),
        status=dict(Counter(r["status"] for r in subset)),
        **{
            k: distribution(r[k] for r in subset)
            for k in (
                "geographic_error_km",
                "forced_error_km",
                "offer_center_error_km",
                "rf_rms_hz",
                "wall_s",
                "native_preparation_wall_s",
                "numerical_stages_wall_s",
                "cpu_s",
                "rss_kib",
            )
        },
    )


def comparison(rows):
    lookup = {(r["condition"], r["arm"], r["method"], r["id"]): r for r in rows}
    paired = {}
    for condition in CONDITIONS:
        for arm in ARMS:
            items = [
                r
                for r in rows
                if (r["condition"], r["arm"], r["method"]) == (condition, arm, trial.CANDIDATE)
            ]
            paired[f"{condition}/{arm}"] = {
                field: distribution(
                    r[field] - stock[field]
                    for r in items
                    if (stock := lookup[condition, arm, trial.CONTROL, r["id"]])[field] is not None
                    and r[field] is not None
                )
                for field in ("geographic_error_km", "rf_rms_hz", "wall_s", "cpu_s", "rss_kib")
            }
    return paired


def calibration_delta(rows):
    zero = {(r["method"], r["condition"], r["id"]): r for r in rows if r["arm"] == "c0"}
    paired = {}
    for method, condition, _ in zero:
        key = f"{method}/{condition}"
        if key in paired:
            continue
        arms = [
            (zero[method, condition, r["id"]], r)
            for r in rows
            if (r["method"], r["condition"], r["arm"]) == (method, condition, "fitted_c")
        ]
        paired[key] = {
            field: distribution(
                b[field] - a[field]
                for a, b in arms
                if a[field] is not None and b[field] is not None
            )
            for field in ("rf_rms_hz", "geographic_error_km")
        }
    return paired


def read_reference(path):
    if path is None:
        return []
    folder = path.parent
    lock = trial.read(path)
    if any(trial.digest(folder / name) != actual for name, actual in lock["files"].items()):
        raise ValueError("the regional numerical reference differs from its seal")
    if "predictions.jsonl.gz" not in lock["files"]:
        raise ValueError("the regional numerical reference seal lacks its prediction archive")
    with gzip.open(folder / "predictions.jsonl.gz", "rt") as archive:
        rows = list(map(json.loads, archive))
    if (
        len(rows) != 2
        or len({r["id"] for r in rows}) != 2
        or any(r["method"] != REFERENCE for r in rows)
    ):
        raise ValueError("compare the original numerical reference only on its sealed two offers")
    return rows


def charts(out, cases, reference_ids, reference_note):
    provenance = [
        "prediction-lock.json",
        "source-lock.json",
        "input-lock.json",
        "scores.csv",
        "score-lock.json",
        "unchanged-v5-preflight.json",
    ]
    names = ("positions.jsonl.gz", "figure-queries.json", *provenance)
    save_json(
        out / "figure-lock.json",
        dict(
            cases=cases,
            files={name: trial.digest(out / name) for name in names},
        ),
    )
    labels = {trial.CANDIDATE: "Phase release", trial.CONTROL: "Base compact"}
    specs = []
    for method, control in (trial.METHODS, tuple(reversed(trial.METHODS))):
        specs.append(
            dict(
                id=f"compact-blind-{method}",
                method=method,
                scope="transfer",
                cases="sealed",
                title=f"{labels[method]} on four new simulated receiver sites",
                caption=(
                    "Physically generated wideband GLRT candidates on the same four locations. "
                    "Both installed releases receive the same single 25 km offer and causal TLE. "
                    "An omitted-region publication counts as a false fix."
                ),
                seal="figure-lock.json",
                queries="figure-queries.json",
                provenance=provenance,
                condition_labels={
                    "containing": "25 km containing offer",
                    "omitted": "Near omitted offer",
                },
                series=[
                    dict(
                        key=key,
                        label=labels[m],
                        file="positions.jsonl.gz",
                        value=m,
                        match=["native_sha256", "catalogue_sha256", "input_sha256"],
                    )
                    for key, m in (("candidate", method), ("stock", control))
                ],
            )
        )
    if reference_ids:
        names = ("reference-positions.jsonl.gz", "reference-queries.json", *provenance)
        save_json(
            out / "reference-figure-lock.json",
            dict(
                cases=reference_ids,
                files={name: trial.digest(out / name) for name in names},
            ),
        )
        specs.append(
            dict(
                id="compact-blind-original-numerical-reference",
                method=REFERENCE,
                scope="transfer",
                cases="sealed",
                title="Original v5 numerical reference on two new-location offers",
                caption=(
                    "One simulated session with matched native inputs and 25 km offers. "
                    "The original numerical engine uses a qualified off-roof harness."
                    + reference_note
                ),
                seal="reference-figure-lock.json",
                queries="reference-queries.json",
                provenance=provenance,
                condition_labels={
                    "containing": "25 km containing offer",
                    "omitted": "Near omitted offer",
                },
                series=[
                    dict(
                        key=key,
                        label=label,
                        file="reference-positions.jsonl.gz",
                        value=m,
                        match=["native_sha256", "catalogue_sha256", "input_sha256"],
                    )
                    for key, label, m in (
                        ("candidate", "Original numerical reference", REFERENCE),
                        ("stock", "Installed phase release", trial.CANDIDATE),
                    )
                ],
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=specs))


def score(work, out, reference_seal):
    seal_path = out / "prediction-lock.json"
    seal = trial.read(seal_path)
    if any(trial.digest(out / f) != d for f, d in seal["files"].items()):
        raise ValueError("scientific predictions changed after sealing")
    pin = trial.read(out / "input-lock.json")
    path = work / "custodian-only.json"
    if trial.digest(path) != pin["private_sha256"]:
        raise ValueError("custodian labels changed after the input commitment")
    reference = read_reference(reference_seal)
    reference_digest = trial.digest(reference_seal) if reference else None
    public = {r["id"]: r for r in trial.read(out / "requests.json")}
    predictions = load_predictions(out, public)
    # Geographic information is first decoded after verifying the prediction commitment.
    private = trial.read(path)
    truth = private["targets"]
    records, queries = [], []
    for row in predictions + reference:
        case, target = public[row["id"]], truth[row["id"]]
        validate_result(row["result"])
        if (
            row["native_sha256"] != case["native_sha256"]
            or row["catalogue_sha256"] != case["catalog_sha256"]
            or row["input_sha256"] != sha256(trial.encoded(case)).hexdigest()
        ):
            raise ValueError("scientific archive mismatched the public native/context binding")
        if case["session"] != target["session"]:
            raise ValueError("geographic evaluator and native schedule refer to different sessions")
        records.extend(row_score(row, case, target, arm) for arm in ARMS)
        if row["method"] == trial.CANDIDATE:
            queries.append(
                dict(
                    id=row["id"],
                    recording=case["session"],
                    condition=target["condition"],
                    truth=target["site"],
                    bindings=dict(input_sha256=row["input_sha256"]),
                )
            )
    score_file = io.StringIO(newline="")
    table = csv.DictWriter(score_file, fieldnames=list(records[0]))
    table.writeheader()
    table.writerows(records)
    write(out / "scores.csv", score_file.getvalue().encode())
    save_json(out / "truth-after-lock.json", private)
    save_json(out / "figure-queries.json", dict(queries=queries))
    reference_ids = [r["id"] for r in reference]
    reference_files = ()
    reference_note = ""
    if reference_ids:
        if len({public[i]["session"] for i in reference_ids}) != 1 or {
            truth[i]["condition"] for i in reference_ids
        } != set(CONDITIONS):
            raise ValueError("the two reference offers do not correspond to one matched session")
        paired = [
            r for r in predictions if r["id"] in reference_ids and r["method"] == trial.CANDIDATE
        ]
        pack(out, "reference-positions.jsonl.gz", reference + paired)
        save_json(
            out / "reference-queries.json",
            dict(
                queries=[q for q in queries if q["id"] in reference_ids],
            ),
        )
        reference_files = ("reference-positions.jsonl.gz", "reference-queries.json")
        omitted = next(r for r in reference if truth[r["id"]]["condition"] == "omitted")
        matched = next(r for r in paired if r["id"] == omitted["id"])
        if omitted["result"]["status"] == "timed_out":
            deadline = omitted["worker_wall_s"]
            reference_note = f" The original omitted offer timed out at {deadline:.0f} s."
        if any(a["latlon"] is not None for a in matched["result"]["arms"].values()):
            reference_note += " Phase release issued a false regional fix."
    save_json(
        out / "summary.json",
        dict(
            cohorts={
                f"{m}/{c}/{a}": cohort(records, m, c, a)
                for m in trial.METHODS
                for c in CONDITIONS
                for a in ARMS
            },
            phase_release_minus_base=comparison(records),
            fitted_minus_zero=calibration_delta(records),
            regional_reference=[r for r in records if r["method"] == REFERENCE],
        ),
    )
    files = (
        "prediction-lock.json",
        "scores.csv",
        "summary.json",
        "truth-after-lock.json",
        "figure-queries.json",
        *reference_files,
    )
    save_json(
        out / "score-lock.json",
        dict(
            files={name: trial.digest(out / name) for name in files},
            reference_terminal_seal_sha256=reference_digest,
        ),
    )
    charts(out, list(public), reference_ids, reference_note)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", type=Path, default=trial.OUT)
    parser.add_argument("--reference-seal", type=Path)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    score(args.work.resolve(), args.out, args.reference_seal)
    if args.render:
        standard.generate(args.out / "charts", evidence=args.out)


if __name__ == "__main__":
    main()
