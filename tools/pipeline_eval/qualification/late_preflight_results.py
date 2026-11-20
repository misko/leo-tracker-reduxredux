"""Score the sealed late stage replay and render the standard roof comparison."""

import argparse
import gzip
from pathlib import Path

from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, thresholds
from ..variants import late_preflight
from . import late_preflight_trial as trial
from .full_receiver_comparison import read, roster_matches, sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

MATERIAL_KM = 0.1
POSITIONS = "positions.jsonl.gz"
ARTIFACTS = (
    "predecision.json.gz",
    "outcomes.json.gz",
    "predecision-lock.json",
    "summary.json",
    "scores.csv",
    POSITIONS,
)


def replay_packet(blind, outcome):
    result = {}
    for arm in ARMS:
        stages = outcome["stages"][arm]
        point = stages["final"] if blind["preflight"]["run"] else stages["incumbent"]
        # With no selected identity repair these are the exact same state and fit.
        rf = (
            stages["final"]["rf_rms_hz"]
            if outcome["decision"]["selected"] is None
            else point["rf_rms_hz"]
        )
        result[arm] = dict(latlon=point["latlon"], rf_rms_hz=rf)
    binding = {k: blind[k] for k in ("id", *trial.MATCH, "request_sha256", "archive_sha256")}
    return [
        dict(
            binding,
            method=method,
            result=dict(
                status="ok",
                boundary=boundary,
                metrics=dict(preflight_run=blind["preflight"]["run"]),
                arms=arms,
            ),
        )
        for method, boundary, arms in (
            (
                trial.METHOD,
                "Archived same-request RF preflight selecting stock or incumbent",
                result,
            ),
            (
                trial.CONTROL,
                "Original archived v5 cavity checkpoint",
                {
                    a: {k: outcome["stages"][a]["cavity"][k] for k in ("latlon", "rf_rms_hz")}
                    for a in ARMS
                },
            ),
        )
    ]


def score_rows(refs, predecision, outcomes, replay):
    for ident, ref in refs.items():
        original = outcomes[ident]
        for arm in ARMS:
            stages = original["stages"][arm]
            points = {name: stages[name]["latlon"] for name in stages}
            point = replay[ident]["result"]["arms"][arm]
            points["preflight"] = point["latlon"]
            if distance_km(points["final"], ref["reference"]["baseline"][arm]["latlon"]) != 0:
                raise ValueError(f"{ident} archive final differs from the frozen baseline")
            yield dict(
                id=ident,
                dataset=ref["group"],
                split="diagnostic" if ident in trial.DIAGNOSTIC else "held",
                arm=arm,
                run_original_late=predecision[ident]["preflight"]["run"],
                original_admitted=original["original_eligibility"][
                    "admitted_reassociation_proposals"
                ],
                original_selected=original["decision"]["selected"],
                moved_addition=stages["cavity"]["x"] != stages["incumbent"]["x"],
                moved_reassociation=stages["incumbent"]["x"] != stages["final"]["x"],
                moved_cavity_to_incumbent_km=distance_km(points["cavity"], points["incumbent"]),
                moved_incumbent_to_final_km=distance_km(points["incumbent"], points["final"]),
                moved_cavity_to_final_km=distance_km(points["cavity"], points["final"]),
                moved_final_to_preflight_km=distance_km(points["final"], points["preflight"]),
                **{f"{k}_error_km": distance_km(p, ref["truth"]) for k, p in points.items()},
                **{f"{k}_rms_hz": r["rf_rms_hz"] for k, r in stages.items()},
                preflight_rms_hz=point["rf_rms_hz"],
            )


def stage_summary(ids, predecision, outcomes):
    bypassed = [outcomes[k] for k in ids if not predecision[k]["preflight"]["run"]]
    all_rows = [outcomes[k] for k in ids]

    def counts(rows):
        return dict(
            calls=len(rows),
            families_ranked=sum(r["original_eligibility"]["observed_families"] for r in rows),
            arm_omissions=sum(r["original_eligibility"]["original_arm_omissions"] for r in rows),
            nominations=sum(len(r["decision"]["targets"]) for r in rows),
            admitted=sum(
                r["original_eligibility"]["admitted_reassociation_proposals"] for r in rows
            ),
            selected=sum(r["decision"]["selected"] is not None for r in rows),
            **{
                key: sum(len(fits) for r in rows for _, (_, fits) in r["decision"][key][1])
                for key in ("control_fits", "candidate_fits")
            },
            original_stage_wall_s={
                key: sum(r["stage_wall_s"][key] for r in rows) for key in trial.STAGES
            },
        )

    return {
        "opportunities": counts(all_rows),
        "bypassed": counts(bypassed),
        "preflight_cpu_s": distribution(predecision[k]["preflight"]["cpu_s"] for k in ids),
        "preflight_wall_s": distribution(predecision[k]["preflight"]["wall_s"] for k in ids),
    }


def geography(rows):
    return {
        "addition_moved": sorted(r["id"] for r in rows if r["moved_addition"]),
        "reassociation_moved": sorted(r["id"] for r in rows if r["moved_reassociation"]),
        "material_position_changes": sorted(
            r["id"] for r in rows if r["moved_cavity_to_final_km"] >= MATERIAL_KM
        ),
        "material_geographic_benefits": sorted(
            r["id"] for r in rows if r["cavity_error_km"] - r["final_error_km"] >= MATERIAL_KM
        ),
        "material_benefits_lost": sorted(
            r["id"] for r in rows if r["preflight_error_km"] - r["final_error_km"] >= MATERIAL_KM
        ),
        "final_endpoints_changed": sorted(
            r["id"] for r in rows if r["moved_final_to_preflight_km"] > 0
        ),
        "stages": {
            k: dict(
                error_km=distribution(r[f"{k}_error_km"] for r in rows),
                within_km=thresholds([r[f"{k}_error_km"] for r in rows]),
                conditional_rms_hz=distribution(r[f"{k}_rms_hz"] for r in rows),
            )
            for k in ("cavity", "incumbent", "final", "preflight")
        },
    }


def publish(source, out):
    lock = read(source / "predecision-lock.json")
    for name, wanted in lock["source_sha256"].items():
        if sha(trial.authority.ROOT / name) != wanted:
            raise ValueError(f"late preflight source changed at {name}")
    if sha(source / "predecision.json") != lock["files"]["predecision.json"]:
        raise ValueError("predecision seal changed")
    blind, outcomes = (read(source / name) for name in ("predecision.json", "outcomes.json"))
    refs, _ = _frozen_roof()
    roster_matches(lock["cases"], refs, "original roof lock")
    for collection in (blind, outcomes):
        roster_matches([r["id"] for r in collection], refs, "late stage replay")
    b, o = [{row["id"]: row for row in collection} for collection in (blind, outcomes)]
    for row in blind:
        go, reason, families = late_preflight.preflight(row["features"])
        original = row["preflight"]
        if (go, reason, list(families)) != (
            original["run"],
            original["reason"],
            original["plausible"],
        ):
            raise ValueError(
                f"{row['id']} original decision cannot replay from its native RF trace"
            )
    predictions = [r for ident in refs for r in replay_packet(b[ident], o[ident])]
    replay = {r["id"]: r for r in predictions if r["method"] == trial.METHOD}
    rows = list(score_rows(refs, b, o, replay))
    groups = dict(
        diagnostic=trial.DIAGNOSTIC,
        held=sorted(set(refs) - set(trial.DIAGNOSTIC)),
        all=sorted(refs),
    )
    save_json(
        out / "summary.json",
        {
            name: dict(
                stage=stage_summary(ids, b, o),
                geography={
                    a: geography([r for r in rows if r["id"] in ids and r["arm"] == a])
                    for a in ARMS
                },
            )
            for name, ids in groups.items()
        },
    )
    for name in ("predecision.json", "outcomes.json"):
        write(out / (name + ".gz"), gzip.compress((source / name).read_bytes(), mtime=0))
    write(out / "predecision-lock.json", (source / "predecision-lock.json").read_bytes())
    csv_file(out / "scores.csv", rows)
    pack(out / POSITIONS, predictions)
    save_json(
        out / "roof-lock.json", dict(cases=sorted(refs), files={n: sha(out / n) for n in ARTIFACTS})
    )
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="late-preflight-roof135",
                    method=trial.METHOD,
                    scope="roof",
                    cases="roof135",
                    title="RF preflight for late v5 recovery on 135 recordings",
                    caption=(
                        "Archive-stage replay from captured cavity RF. The guard selects "
                        "the saved post-addition incumbent or the original full late result "
                        "on the same request."
                    ),
                    seal="roof-lock.json",
                    provenance=["scores.csv", "summary.json", "predecision-lock.json"],
                    series=[
                        dict(
                            key="one",
                            label="Archived RF preflight replay",
                            file=POSITIONS,
                            value=trial.METHOD,
                        ),
                        dict(
                            key="stock",
                            label="Original cavity cutoff",
                            file=POSITIONS,
                            value=trial.CONTROL,
                            match=trial.MATCH,
                        ),
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    publish(args.input, local_output(args.output))
