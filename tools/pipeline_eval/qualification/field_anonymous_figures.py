"""Build standard transfer figures from the sealed anonymous field replay."""

import argparse
import json
from pathlib import Path

from ..__main__ import read_predictions, save_json
from ..scoring import ARMS
from . import field_anonymous_trial as trial
from . import screening_figures as standard
from .armijo_finish_results import pack


def controls(job, prediction, historical):
    old = historical.get(job["query_id"], {})
    forced = (
        [float(old[f"forced_rf_{k}"]) for k in ("latitude", "longitude")]
        if old.get("forced_rf_latitude")
        else None
    )
    public = (
        [float(old[f"receiver_{k}"]) for k in ("latitude", "longitude")]
        if old.get("receiver_latitude")
        else None
    )
    null = prediction["result"]["metrics"].get("time_control_forced_latlon")
    variants = (
        ("archived_field_grid", forced, public, "Earlier full-offer Doppler grid", bool(old)),
        ("field_time_shift_control", null, None, "Recomputed shifted timestamps", null is not None),
    )
    for method, point, fix, boundary, available in variants:
        yield dict(
            id=job["id"],
            method=method,
            observation_sha256=job["source_observation_sha256"],
            result=dict(
                status="ok" if fix else "withheld" if available else "unavailable",
                reason=None
                if fix
                else "diagnostic_or_archived_withhold"
                if available
                else "no_matched_estimate",
                boundary=boundary,
                metrics={},
                arms={name: dict(latlon=fix, forced_latlon=point) for name in ARMS},
            ),
        )


def describe(evidence):
    lock = json.loads((evidence / "prediction-lock.json").read_bytes())
    scoring = json.loads((evidence / "score-lock.json").read_bytes())
    for name, expected in (lock["files"] | scoring["files"]).items():
        trial.authority._read(evidence / name, expected)
    plan = json.loads((evidence / "source-lock.json").read_bytes())
    raw_receipt = (trial.authority.STUDY / "field-receipt.json").read_bytes()
    receipt = json.loads(raw_receipt)
    if receipt["sealed_truth_sha256"] != plan["scoring_truth_sha256"]:
        raise ValueError("figure must use the same held geographic authority")
    survey = json.loads(trial.authority._verified_truth(receipt))["cases"]
    truth = {r["pair"]: r["latlon"] for r in survey if r["condition"] == "present"}
    old_path = trial.authority.STUDY / "results/field/per_query.csv"
    trial.authority._read(old_path, plan["sources"][str(old_path.relative_to(trial.ROOT))])
    older = trial._reference()
    archive = read_predictions(evidence / "positions.jsonl.gz")
    if set(archive) != {job["id"] for job in plan["queries"]}:
        raise ValueError("figure inputs do not cover the complete physical panel")
    charts = []
    for panel in ("all", "holdout"):
        jobs = [job for job in plan["queries"] if panel in ("all", job["cohort"])]
        queries, rows = [], []
        for job in jobs:
            prediction = archive[job["id"]]
            if prediction["input_sha256"] != job["input_sha256"]:
                raise ValueError("figure source has the wrong worker input binding")
            observation_digest = job["source_observation_sha256"]
            rows.extend(
                [
                    dict(prediction, observation_sha256=observation_digest),
                    *controls(job, prediction, older),
                ]
            )
            queries.append(
                dict(
                    id=job["id"],
                    condition=job["mode"],
                    recording=job["capture"],
                    truth=truth[job["pair"]],
                    bindings=dict(observation_sha256=observation_digest),
                )
            )
        name = f"figure-{panel}-positions.jsonl.gz"
        qname, lname = f"figure-{panel}-queries.json", f"figure-{panel}-lock.json"
        pack(evidence, name, rows)
        save_json(evidence / qname, dict(queries=queries))
        provenance = list(dict.fromkeys([*lock["files"], *scoring["files"], "score-lock.json"]))
        save_json(
            evidence / lname,
            dict(
                cases=[q["id"] for q in queries],
                files={
                    file: trial.digest((evidence / file).read_bytes())
                    for file in (name, qname, *provenance)
                },
            ),
        )
        caption = (
            "Prepared measured curves from one installation. Worldwide geometry has no site prior. "
            "The archived grid supplies regional comparisons only. "
            "Both c arms coincide at one RF."
        )
        subject = "four held physical sites" if panel == "holdout" else "all eleven field captures"
        charts.append(
            dict(
                id=f"field_anonymous_doppler_{panel}",
                method=trial.METHOD,
                scope="transfer",
                title=f"Shared receiver drift on {subject}",
                caption=caption,
                cases="sealed",
                seal=lname,
                queries=qname,
                provenance=provenance,
                condition_labels={
                    "worldwide": "Fixed worldwide lattice",
                    "containing": "Four offers · site included",
                    "omitted": "Four offers · site omitted",
                },
                series=[
                    dict(
                        key="candidate",
                        label="Shared drift · published",
                        file=name,
                        forced_label="Shared drift · forced",
                        value=trial.METHOD,
                    ),
                    dict(
                        key="stock",
                        label="Archived grid · published",
                        file=name,
                        forced_label="Archived grid · forced",
                        value="archived_field_grid",
                    ),
                    dict(
                        key="one",
                        label="Time shift · diagnostic",
                        file=name,
                        forced_label="Time shift · forced",
                        value="field_time_shift_control",
                    ),
                ],
            )
        )
    save_json(evidence / "figures.json", dict(version=1, charts=charts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=trial.OUT)
    parser.add_argument("--render", type=Path)
    args = parser.parse_args()
    describe(args.evidence)
    if args.render is not None:
        standard.generate(args.render, evidence=args.evidence)


if __name__ == "__main__":
    main()
