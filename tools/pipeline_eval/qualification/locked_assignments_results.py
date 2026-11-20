"""Publish geographic and conditional-RF effects of fixed assignments."""

import argparse
import gzip
import json
from collections import Counter, defaultdict

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import locked_assignments_trial as trial
from . import rescue_attribution
from .full_held_scores import held_references
from .full_v5_check import _sha
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file

REPORT = trial.REPORT
METHOD = "locked_assignments"
CONDITIONS = ("stock", "union", "stock_identity", "union_identity")
LANDMARKS = ("stock_identity", "union_identity")
read = whole_iq.read


def compare_points(stock, union):
    shared = stock.keys() & union.keys()
    split, merged = defaultdict(set), defaultdict(set)
    shifts = Counter()
    for oid in shared:
        a, b = stock[oid], union[oid]
        split[a["group"]].add(b["group"])
        merged[b["group"]].add(a["group"])
        if a["norad"] != b["norad"]:
            shifts[a["norad"], b["norad"]] += 1
    return dict(
        stock=len(stock),
        union=len(union),
        common=len(shared),
        stock_only=len(stock.keys() - union.keys()),
        union_only=len(union.keys() - stock.keys()),
        changed_norad=sum(shifts.values()),
        stock_groups_split=sum(len(v) > 1 for v in split.values()),
        union_groups_merge_stock=sum(len(v) > 1 for v in merged.values()),
        common_points_in_split_groups=sum(len(split[stock[k]["group"]]) > 1 for k in shared),
        common_points_in_merged_groups=sum(len(merged[union[k]["group"]]) > 1 for k in shared),
        reassigned=[
            dict(stock=a, union=b, points=count) for (a, b), count in sorted(shifts.items())
        ],
    )


def scientific(result):
    return (
        result["status"],
        result["arms"],
        {key: value for key, value in result["metrics"].items() if key != "stage_s"},
    )


def bound_attempt(work, plan, attempt):
    ident, role = (attempt[k] for k in ("id", "role"))
    base = work / ident / role
    if (
        attempt["input"] != plan["cases"][ident]["inputs"][role]
        or attempt["source_plan_sha256"] != _sha(REPORT / "plan.json")
        or attempt["cpu"] != plan["pins"][ident]
    ):
        raise ValueError("recording, worker or CPU pin differs from the input plan")
    if role == "stock" and "union_assignment_sha256" in attempt:
        whole_iq.checked(base.parent / "union/capture.json", attempt["union_assignment_sha256"])
    raw = {}
    files = attempt["files"]
    for name, digest in files.items():
        path = whole_iq.checked(base / name, digest)
        archive = REPORT / f"{ident}-{role}-{name}.gz"
        write(archive, gzip.compress(path.read_bytes(), mtime=0))
        raw[name] = read(path) if name.endswith(".json") else None
    outcome = raw.get("resources.json")
    if outcome and any(
        outcome[part]["memory.max"] != plan["memory_bytes"]
        or outcome[part]["memory.swap.max"]
        or outcome[part]["memory.swap.current"]
        for part in ("start", "end")
    ):
        raise ValueError("worker ran outside its physical resource cap")
    if not attempt["status"] and not outcome:
        raise ValueError("successful fit lacks resource receipt")
    return raw


def no_result(attempt, reason):
    timeout = any("timeout" in status for status in attempt["service"])
    return dict(
        status="timed_out" if timeout else "failed",
        reason=reason,
        boundary="Phase-release fixed-assignment continuous position refit",
        arms={arm: dict(latlon=None) for arm in ARMS},
        metrics={},
    )


def finish(work):
    read_sealed = rescue_attribution.sealed
    planfile = read_sealed(REPORT, "prediction-lock.json", "plan.json")
    plan = read(planfile)
    attempts = read(read_sealed(REPORT, "prediction-lock.json", "attempts.json"))
    parent = rescue_attribution.parent.REPORT
    whole_iq.checked(parent / "figure-lock.json", plan["parent_sha256"])
    with gzip.open(read_sealed(parent, "figure-lock.json", "positions.jsonl.gz")) as stream:
        prior = {
            (r["id"], "union" if r["condition"] == "rescue" else "stock"): r
            for r in map(json.loads, stream)
            if r["condition"] in ("stock", "rescue")
        }
    if len(attempts) != 4 or {(r["id"], r["role"]) for r in attempts} != prior.keys():
        raise ValueError("missing authentic stock or union attempt")
    receipts = {
        (attempt["id"], attempt["role"]): bound_attempt(work, plan, attempt) for attempt in attempts
    }
    _, refs = held_references(None, trial.PINS)
    reference = {r["id"]: r for r in refs}
    results, differences, scores, timings = [], {}, [], []
    for ident in trial.PINS:
        earlier = reference[ident]
        stock_run = receipts[ident, "stock"]
        union_run = receipts[ident, "union"]
        a, b = (run.get("capture.json") for run in (stock_run, union_run))
        refits = stock_run.get("refits.json")
        recorded = {}
        for name, output in (("stock", a), ("union", b)):
            original = prior[ident, name]
            spec = plan["cases"][ident]
            input_binding = spec["inputs"][name]
            if (
                original["native_sha256"] != input_binding["native_sha256"]
                or original["original_request_sha256"] != spec["original_request_sha256"]
                or original["catalog_sha256"] != spec["catalogue"]
                or original["tile"] != spec["tile"]
            ):
                raise ValueError("parent method used different native input, offer, or catalogue")
            recorded[name] = (
                scientific(original["result"]) == scientific(output["production"])
                if output
                else None
            )
        differences[ident] = dict(
            original_parity=recorded,
            stock_replay_exact=refits.get("stock_replay_exact") if refits else None,
        )
        if all(run and "final" in run for run in (a, b)):
            differences[ident].update(
                conservative=compare_points(
                    a["conservative"]["curved"], b["conservative"]["curved"]
                ),
                final=compare_points(a["final"]["curved"], b["final"]["curved"]),
                predictive=compare_points(a["final"]["predictive"], b["final"]["predictive"]),
                decisions={
                    method: dict(
                        fit_path=run["role"],
                        cavity_offered=run["cavity_offered"],
                        cavity_adopted=run["cavity_adopted"],
                        cavity_trials=run["cavity_trials"],
                        signed=run["signed"],
                        signed_to_final_km={
                            arm: distance_km(
                                run["signed"][arm]["latlon"],
                                run["production"]["arms"][arm]["latlon"],
                            )
                            for arm in ARMS
                        },
                    )
                    for method, run in (("stock", a), ("union", b))
                },
            )
        if refits:
            differences[ident]["match"] = {
                k: refits[k]
                for k in (
                    "counts",
                    "shifts",
                    "original_stock_predictive_points",
                    "matched_predictive_points",
                )
            }
        stock_attempt = next(r for r in attempts if (r["id"], r["role"]) == (ident, "stock"))
        for condition in CONDITIONS:
            if condition in LANDMARKS:
                reason = "Matched support worker ended before a usable paired result"
                if refits and refits.get("stock_replay_exact") and all(recorded.values()):
                    result = refits["fits"].get(condition) or no_result(
                        stock_attempt, "No common curved observations survived the identity match"
                    )
                else:
                    result = no_result(stock_attempt, reason)
            else:
                # Show the authenticated parent endpoints, and report fresh replay parity above.
                result = prior[ident, condition]["result"]
            validate_result(result)
            original = prior[ident, "stock"]
            results.append(
                {
                    key: original[key]
                    for key in (
                        "id",
                        "tile",
                        "catalog_sha256",
                        "original_request_sha256",
                        "stock_native_sha256",
                        "paired_capture_sha256",
                    )
                }
                | dict(
                    method=f"{METHOD}_{condition}",
                    condition=condition,
                    union_native_sha256=prior[ident, "union"]["native_sha256"],
                    native_sha256=prior[ident, "union" if condition == "union" else "stock"][
                        "native_sha256"
                    ],
                    result=result,
                )
            )
            for arm in ARMS:
                value = result["arms"][arm]
                error = distance_km(value["latlon"], earlier["truth"])
                scores.append(
                    dict(
                        id=ident,
                        condition=condition,
                        arm=arm,
                        status=result["status"],
                        geographic_error_km=error,
                        forced_error_km=distance_km(value.get("forced_latlon"), earlier["truth"]),
                        conditional_rms_hz=value.get("rf_rms_hz"),
                        withheld_stock_rms_hz=value.get("withheld_stock_rms_hz"),
                        objective=value.get(
                            "frequency_objective", result["metrics"].get(f"{arm}_frequency_score")
                        ),
                        failed_curved_gates=value.get("failed_curved_gates"),
                        **{
                            f"v5_{role}_error_km": earlier["reference"][role][arm]["error_km"]
                            for role in ROLES
                        },
                    )
                )
        for role, raw in (("stock", stock_run), ("union", union_run)):
            attempt = next(r for r in attempts if (r["id"], r["role"]) == (ident, role))
            profile = raw.get("resources.json") or {}
            capture = raw.get("capture.json") or {}
            timings.append(
                dict(
                    id=ident,
                    scope=f"{role}_service",
                    pin=attempt["cpu"],
                    exit_code=attempt["status"],
                    service_wall_s=attempt["supervisor_wall_s"],
                    internal_wall_s=profile.get("wall_s"),
                    cpu_s=profile.get("cpu_s"),
                    production_wall_s=capture.get("wall_s"),
                    production_cpu_s=capture.get("cpu_s"),
                    peak_bytes=profile.get("end", {}).get("memory.peak"),
                )
            )
        for label, measured in (refits or {}).get("measures", {}).items():
            timings.append(
                dict(
                    id=ident,
                    scope=label,
                    pin=plan["pins"][ident],
                    exit_code=0,
                    service_wall_s=None,
                    internal_wall_s=measured["wall_s"],
                    cpu_s=measured["cpu_s"],
                    production_wall_s=None,
                    production_cpu_s=None,
                    peak_bytes=None,
                )
            )
    write(REPORT / "positions.jsonl.gz", compressed_rows(results))
    save_json(REPORT / "assignment-effects.json", differences)
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "resources.csv", timings)
    figures()


def figures():
    provenance = ("prediction-lock.json", "assignment-effects.json", "scores.csv", "resources.csv")
    files = ("positions.jsonl.gz", *provenance)
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=list(trial.PINS),
            files={name: _sha(REPORT / name) for name in files},
        ),
    )
    matched = [
        "tile",
        "catalog_sha256",
        "original_request_sha256",
        "stock_native_sha256",
        "union_native_sha256",
        "paired_capture_sha256",
    ]
    charts = []
    for condition, label in (
        ("stock_identity", "Common support with stock identities"),
        ("union_identity", "Common support with coherent union identities"),
    ):
        series = [
            dict(
                key=key,
                value=f"{METHOD}_{name}",
                file=files[0],
                label=text,
                native_field="paired_capture_sha256",
                match=matched,
                **({"forced_label": f"{label}, failed original gates"} if key == "one" else {}),
            )
            for key, name, text in (
                ("one", condition, label),
                ("stock", "stock", "Unrestricted stock"),
                ("one_native_factors", "union", "Unrestricted union"),
            )
        ]
        charts.append(
            dict(
                id=f"locked-assignments-{condition}",
                method=f"{METHOD}_{condition}",
                scope="roof",
                cases="sealed",
                seal="figure-lock.json",
                title=label,
                caption=(
                    "Diagnostic refits use identical shared curved observations and original stock "
                    "groups, CFO and aliases. The plot includes the genuine unrestricted parents."
                ),
                provenance=list(provenance),
                series=series,
            )
        )
    save_json(REPORT / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    finish(parser.parse_args().work)
