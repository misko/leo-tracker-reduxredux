"""Score cgroup standalone distribution transfer after verifying the prediction seal."""

import gzip

from ..__main__ import encoded, save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import cavity_payload_transfer as trial
from . import screening_figures
from .fresh_scenes import _read, _sha
from .native_joint_full_results import roi_margin
from .transfer_budget_results import sealed

METHODS = tuple(f"v5_cavity_payload_{variant}" for variant in trial.PACKAGES)
BINDINGS = (
    "input_sha256",
    "native_sha256",
    "catalog_sha256",
    "history_sha256",
    "track_config_sha256",
)
ARCHIVE = "figure-positions.jsonl.gz"
CONDITIONS = {"original": "Containing tile supplied", "far-outside": "Correct region omitted"}


def science(result):
    return dict(result, metrics={k: v for k, v in result["metrics"].items() if k != "stage_s"})


def scored_inputs(output):
    sealed(output)
    predictions, planned, truth, public, locks = (
        _read(output / name)
        for name in (
            "predictions.json",
            "requests.json",
            "released-labels.json",
            "public-captures.json",
            "input-lock.json",
        )
    )
    records = {(r["id"], r["method"]): r for r in predictions}
    bound = {r["id"]: r for r in planned}
    if (
        len(predictions) != 8
        or len(bound) != 4
        or records.keys() != {(ident, method) for ident in bound for method in METHODS}
    ):
        raise ValueError("both packages must hold the complete sealed execution roster")
    for (ident, _), actual in records.items():
        if any(actual[key] != value for key, value in bound[ident].items()):
            raise ValueError("paired scientific input changed")
        if actual["runtime"]["proof"] and actual["runtime"]["proof"][0]["memory"] != trial.MEMORY:
            raise ValueError("cgroup limit differs from the frozen experiment")
    if len(truth) != 2 or truth.keys() != public.keys():
        raise ValueError("expected two independent sealed capture documents")
    cases = {}
    for capture, data in sorted(truth.items(), key=lambda r: -r[1]["location"][0]):
        for folder, material in (("public", public[capture]), ("private", data)):
            if locks[f"{folder}/{capture}.json"] != trial.prior.INPUTS.cold._sha(
                encoded(material) + b"\n"
            ):
                raise ValueError("released target/document differs from its commitment")
        for ident, role in data["roles"].items():
            if ident in bound:
                if bound[ident]["native_sha256"] != locks[f"public/{capture}.complete.json"]:
                    raise ValueError("completed native authority is unsealed")
                cases[ident] = dict(role=role, site=data["location"], capture=capture)
    if cases.keys() != bound.keys():
        raise ValueError("scorer labels do not cover the source-locked roster")
    return records, cases


def score(output):
    source, cases = scored_inputs(output)
    scores, pairs, queries = [], [], []
    for ident, label in cases.items():
        small, full = [source[ident, m] for m in METHODS]
        row, result = small, small["result"]
        role, truth = label["role"], label["site"]
        queries.append(
            dict(
                id=ident,
                recording=label["capture"],
                truth=truth,
                condition=CONDITIONS[role],
                bindings={k: row[k] for k in BINDINGS},
            )
        )
        both_completed = all(
            item["exit_code"] == 0 and item["runtime"]["origins"] for item in (small, full)
        )
        pairs.append(
            dict(
                id=ident,
                role=role,
                both_completed=both_completed,
                scientific_parity=(science(result) == science(full["result"]))
                if both_completed
                else None,
                endpoint_delta_km={
                    arm: distance_km(
                        result["arms"].get(arm, {}).get("latlon"),
                        full["result"]["arms"].get(arm, {}).get("latlon"),
                    )
                    for arm in ARMS
                },
                runtime={
                    item["method"]: dict(
                        wall_s=item["wall_s"],
                        status=item["result"]["status"],
                        **{
                            k: (item["runtime"]["finish"] or [{}])[0].get(k)
                            for k in ("cgroup_cpu_s", "cgroup_peak", "peak_rss_kib", "paths")
                        },
                    )
                    for item in (small, full)
                },
            )
        )
        for row in (small, full):
            fit = row["result"]
            for arm in ARMS:
                part = fit["arms"].get(arm, {})
                fix = part.get("latlon")
                scores.append(
                    dict(
                        id=ident,
                        capture_id=label["capture"],
                        latitude=truth[0],
                        role=role,
                        method=row["method"],
                        arm=arm,
                        status=fit["status"],
                        reason=fit.get("reason"),
                        error_km=distance_km(fix, truth),
                        rf_rms_hz=part.get("rf_rms_hz"),
                        frequency_score=fit["metrics"].get(f"{arm}_frequency_score"),
                        true_tile_margin_km=roi_margin(truth, row["tile"]),
                        false_publication=role == "far-outside" and fix is not None,
                    )
                )
    summary = []
    for method, arm, role in ((m, a, r) for m in METHODS for a in ARMS for r in CONDITIONS):
        chosen = [
            row for row in scores if (row["method"], row["arm"], row["role"]) == (method, arm, role)
        ]
        summary.append(
            dict(
                method=method,
                arm=arm,
                role=role,
                attempts=len(chosen),
                publication=sum(r["error_km"] is not None for r in chosen),
                false_publication=sum(r["false_publication"] for r in chosen),
                position_km=distribution(r["error_km"] for r in chosen),
                conditional_rf_hz=distribution(r["rf_rms_hz"] for r in chosen),
            )
        )
    save_json(output / "scores.json", dict(rows=scores, comparison=pairs, summary=summary))
    write(
        output / ARCHIVE,
        gzip.compress(b"".join(encoded(r) + b"\n" for r in source.values()), mtime=0),
    )
    return queries


def render(output, roster):
    query, lock = "figure-queries.json", "figure-lock.json"
    proof = ("prediction-lock.json", "source-lock.json", "input-lock.json")
    save_json(output / query, dict(queries=roster))
    save_json(
        output / lock,
        dict(
            cases=[q["id"] for q in roster],
            files={name: _sha(output / name) for name in (*proof, query, ARCHIVE)},
        ),
    )
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="standalone-cavity-payload-transfer",
                    method=METHODS[0],
                    scope="transfer",
                    cases="sealed",
                    title="Reduced and full standalone cavity on two new simulated sites",
                    caption="Paired capped replays with identical native GLRT and TLE inputs.",
                    queries=query,
                    seal=lock,
                    provenance=list(proof),
                    series=[
                        dict(
                            label="Reduced standalone",
                            key="candidate",
                            file=ARCHIVE,
                            value=METHODS[0],
                        ),
                        dict(
                            label="Full standalone",
                            key="stock",
                            file=ARCHIVE,
                            value=METHODS[1],
                            match=list(BINDINGS),
                        ),
                    ],
                )
            ],
        ),
    )
    screening_figures.generate(output / "figures", evidence=output)


if __name__ == "__main__":
    render(trial.REPORT, score(trial.REPORT))
