"""Score parent, published and rejected cavity positions at their measured boundaries."""

import argparse
import gzip
import json

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import cavity_replay_trial as trial
from . import rescue_attribution, support_cross_trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .locked_assignments_results import scientific
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file

REPORT = trial.REPORT
CONDITIONS = ("challenger", "merged", "stock")
METHOD = "stock_cavity_replay"
read = whole_iq.read


def parents(plan):
    for name, digest in plan["parents"].items():
        whole_iq.checked(ROOT / name, digest)
    two = rescue_attribution.parent.REPORT
    x = rescue_attribution.sealed(two, "figure-lock.json", "positions.jsonl.gz")
    result = {}
    with gzip.open(x) as stream:
        for row in map(json.loads, stream):
            if row["condition"] in ("stock", "rescue"):
                role = "merged" if row["condition"] == "rescue" else "stock"
                result[row["id"], role] = row
    y = rescue_attribution.sealed(
        support_cross_trial.REPORT, "prediction-lock.json", "predictions.jsonl.gz"
    )
    with gzip.open(y) as stream:
        for row in map(json.loads, stream):
            if row["id"] == trial.REPLICATION and row["condition"] in ("wide", "restore"):
                role = "merged" if row["condition"] == "restore" else "stock"
                result[row["id"], role] = row
    for (ident, role), row in result.items():
        cell = plan["cases"][ident]
        if (
            row["native_sha256"] != cell["inputs"][role]["native_sha256"]
            or row["tile"] != cell["tile"]
            or row["catalog_sha256"] != cell["catalogue"]
            or row["original_request_sha256"] != cell["original_request_sha256"]
        ):
            raise ValueError("reference position did not use the declared native input")
    return result


def reference_point(row, arm):
    original = row["result"]
    return original["arms"][arm] | dict(
        frequency_objective=original["metrics"].get(f"{arm}_frequency_score"),
    )


def witnessed(work, plan):
    plan_digest = _sha(REPORT / "plan.json")
    attempts = read(rescue_attribution.sealed(REPORT, "prediction-lock.json", "attempts.json"))
    if len(attempts) != 2 * len(trial.PINS) or {(row["id"], row["role"]) for row in attempts} != {
        (ident, name) for ident in trial.PINS for name in ("stock", "merged")
    }:
        raise ValueError("the three predeclared cases require both physical attempts")
    records, resources = {}, []
    for row in attempts:
        ident, role = row["id"], row["role"]
        folder = work / ident / role
        if row["plan_sha256"] != plan_digest or row["cpu"] != plan["pins"][ident]:
            raise ValueError("physical replay invalidated its plan")
        whole_iq.checked(folder / "service.log", row["log_sha256"])
        if role == "merged" and row["stock_prior_sha256"]:
            whole_iq.checked(folder.parent / "stock/outcome.json", row["stock_prior_sha256"])
        snapshots = [folder / "service.log"]
        result = None
        if row["result_sha256"]:
            path = whole_iq.checked(folder / "outcome.json", row["result_sha256"])
            snapshots.append(path)
        if row["returncode"] == 0 and row["result_sha256"]:
            result = read(path)
            for edge in ("start", "end"):
                m = result["resources"][edge]
                if (
                    m["memory.max"] != plan["memory"]
                    or m["memory.swap.max"]
                    or m["memory.swap.current"]
                ):
                    raise ValueError("physical cap was not retained")
        if row["returncode"] == 0 and result is None:
            raise ValueError("successful service missing scientific outcome")
        for file in snapshots:
            write(
                REPORT / f"{ident}-{role}-{file.name}.gz", gzip.compress(file.read_bytes(), mtime=0)
            )
        records[ident, role] = row, result
        extra = result or {}
        usage = extra.get("resources", {})
        resources.append(
            dict(
                id=ident,
                role=role,
                cpu=row["cpu"],
                returncode=row["returncode"],
                service_wall_s=row["supervisor_wall_s"],
                cpu_s=usage.get("cpu_s"),
                inner_wall_s=usage.get("wall_s"),
                peak_bytes=usage.get("end", {}).get("memory.peak"),
                extra_screen_cpu_s=extra.get("extra_screen", {}).get("cpu_s"),
                forced_refit_cpu_s=extra.get("diagnostic_refit", {}).get("cpu_s"),
            )
        )
    return records, resources


def outcome(witness, baseline, stock_match):
    attempt, item = witness
    if item is None or not stock_match:
        timeout = any("timeout" in line for line in attempt["terminal"])
        return dict(
            status="timed_out" if timeout else "failed",
            reason="Stock prior or merged numerical service could not be reproduced",
            boundary="Saved merged GLRT through one stock-derived cavity challenger",
            arms={arm: dict(latlon=None) for arm in ARMS},
            metrics={},
        )
    production = item["production"]
    ordinary = item.get("ordinary_arms")
    if production["status"] == "ok" and (
        (ordinary and ordinary != {a: reference_point(baseline, a) for a in ARMS})
        or (not item["accepted"] and production["arms"] != baseline["result"]["arms"])
    ):
        raise ValueError("the ordinary branch failed its archived position/RF control")
    return dict(
        production,
        arms={
            arm: values
            | (
                dict(
                    forced_latlon=item["forced"][arm]["latlon"],
                    forced_rf_rms_hz=item["forced"][arm]["rf_rms_hz"],
                )
                if item.get("forced")
                else {}
            )
            for arm, values in production["arms"].items()
        },
    )


def publish(work):
    plan = read(rescue_attribution.sealed(REPORT, "prediction-lock.json", "plan.json"))
    prior = parents(plan)
    records, usage = witnessed(work, plan)
    _, criteria = held_references(None, trial.PINS)
    refs = {r["id"]: r for r in criteria}
    positions, scores, selection = [], [], {}
    for ident, case in plan["cases"].items():
        stock, merged = (prior[ident, role] for role in ("stock", "merged"))
        _, donor = records[ident, "stock"]
        stock_match = donor is not None and scientific(donor["production"]) == scientific(
            stock["result"]
        )
        _, replay = records[ident, "merged"]
        selection[ident] = dict(
            stock_replay_matches=stock_match,
            stock_ranked_hints=len(donor["hints"]) if donor else 0,
            **{k: v for k, v in (replay or {}).items() if k not in {"production", "resources"}},
        )
        fits = dict(
            stock=stock["result"],
            merged=merged["result"],
            challenger=outcome(records[ident, "merged"], merged, stock_match),
        )
        for condition, result in fits.items():
            validate_result(result)
            authority = stock if condition == "stock" else merged
            positions.append(
                dict(
                    id=ident,
                    cohort=case["cohort"],
                    method=f"{METHOD}_{condition}",
                    result=result,
                    tile=case["tile"],
                    catalog_sha256=case["catalogue"],
                    original_request_sha256=case["original_request_sha256"],
                    stock_native_sha256=case["inputs"]["stock"]["native_sha256"],
                    merged_native_sha256=case["inputs"]["merged"]["native_sha256"],
                    native_sha256=authority["native_sha256"],
                    paired_capture_sha256=authority["paired_capture_sha256"],
                )
            )
            ref = refs[ident]
            for arm, value in result["arms"].items():
                scores.append(
                    dict(
                        id=ident,
                        method=condition,
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(value["latlon"], ref["truth"]),
                        forced_error_km=distance_km(value.get("forced_latlon"), ref["truth"]),
                        conditional_rms_hz=value.get("rf_rms_hz"),
                        forced_conditional_rms_hz=value.get("forced_rf_rms_hz"),
                        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                        **{
                            f"v5_{name}_error_km": ref["reference"][name][arm]["error_km"]
                            for name in ROLES
                        },
                    )
                )
    write(REPORT / "positions.jsonl.gz", compressed_rows(positions))
    save_json(REPORT / "candidate-evidence.json", selection)
    csv_file(REPORT / "resources.csv", usage)
    csv_file(REPORT / "scores.csv", scores)
    figures(plan)


def figures(plan):
    provenance = ("prediction-lock.json", "candidate-evidence.json", "resources.csv", "scores.csv")
    files = ("positions.jsonl.gz", *provenance)
    fields = [
        "tile",
        "catalog_sha256",
        "original_request_sha256",
        "paired_capture_sha256",
        "stock_native_sha256",
        "merged_native_sha256",
    ]
    charts = []
    for cohort, tag in (
        ("negative-rescue", "negative-rescue"),
        ("restore-only replication", "restore-only"),
    ):
        cases = [k for k, row in plan["cases"].items() if row["cohort"] == cohort]
        seal = f"{tag}-figure-lock.json"
        save_json(
            REPORT / seal,
            dict(
                cases=cases,
                files={name: _sha(REPORT / name) for name in files},
            ),
        )
        charts.append(
            dict(
                id=f"stock-cavity-replay-{tag}",
                method=f"{METHOD}_challenger",
                scope="roof",
                cases="sealed",
                seal=seal,
                provenance=list(provenance),
                title=f"One stock-derived cavity challenger · {cohort}",
                caption=(
                    "The candidate uses the same merged observations and normal cavity acceptance. "
                    "A rejected numerical endpoint is diagnostic. Stock and merged controls are "
                    "authenticated parent measurements."
                ),
                series=[
                    dict(
                        key=key,
                        file=files[0],
                        value=f"{METHOD}_{name}",
                        label=label,
                        native_field="paired_capture_sha256",
                        where={"cohort": cohort},
                        match=fields,
                        **({"forced_label": "Rejected challenger"} if key == "one" else {}),
                    )
                    for key, name, label in (
                        ("one", "challenger", "Actual challenger-enabled receiver"),
                        ("stock", "stock", "Stock wide"),
                        ("one_native_factors", "merged", "Ordinary merged input"),
                    )
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    publish(parser.parse_args().work)
