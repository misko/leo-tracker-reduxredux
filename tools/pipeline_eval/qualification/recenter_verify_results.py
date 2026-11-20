"""Compare two-pass native verification with the independently timed first fit."""

import argparse
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution
from . import boundary_roof_results as edge
from . import recenter_verify_trial as trial

phase = trial.phase
METHODS = trial.METHODS
VERIFIER, STOCK = METHODS


def parity(records):
    output = {}
    for ident, current in records[VERIFIER].items():
        stock = records[STOCK][ident]
        first = current.get("first")
        graph = current.get("observation_sha256")
        if first is None or graph is None or stock.get("observation_sha256") is None:
            output[ident] = False
            continue
        prior = stock["result"]
        if (
            graph != stock["observation_sha256"]
            or any(first.get(k) != prior.get(k) for k in ("status", "reason", "arms"))
            or first["metrics"].get("clock_fit") != prior["metrics"].get("clock_fit")
        ):
            raise ValueError("the in-process first fit differs from the matched standalone result")
        output[ident] = True
    return output


def pair_rows(rows, records, labels):
    for row in rows:
        ident, arm, method = row["id"], row["arm"], row["method"]
        current = records[method][ident]
        seen = current.get("verification", {})
        second = seen.get("result", {})
        point = second.get("arms", {}).get(arm, {})
        worker_stage = current.get("stages", {}).get("verification_fit", {})
        row.update(
            expanded_attempted=seen.get("attempted"),
            expanded_status=second.get("status"),
            expanded_reason=second.get("reason"),
            expanded_geodesic_shift_km=seen.get("shifts_km", {}).get(arm),
            expanded_inside_original=seen.get("expanded_inside_original", {}).get(arm),
            expanded_forced_error_km=distance_km(
                point.get("forced_latlon"), labels[ident]["truth"]
            ),
            expanded_conditional_rms_hz=point.get("rf_rms_hz"),
            expanded_held_score=point.get("held_score"),
            expanded_stage_cpu_s=worker_stage.get("cpu_s"),
            expanded_stage_wall_s=worker_stage.get("wall_s"),
        )


def paired_summary(rows, paired):
    by_key = {(r["method"], r["id"], r["arm"]): r for r in rows}
    summaries = []
    for arm in ARMS:
        for condition in edge.CONDITIONS:
            verify = [
                r
                for r in rows
                if r["method"] == VERIFIER and r["condition"] == condition and r["arm"] == arm
            ]
            if not verify:
                continue
            controls = [by_key[STOCK, r["id"], arm] for r in verify]
            pairs = list(zip(verify, controls, strict=True))
            kept = [a for a, b in pairs if a["status"] == b["status"] == "ok"]
            lost = [b for a, b in pairs if a["status"] != "ok" and b["status"] == "ok"]
            summaries.append(
                dict(
                    arm=arm,
                    condition=condition,
                    scheduled=len(verify),
                    exact_first_fit=sum(paired[r["id"]] for r in verify),
                    control_published=sum(r["status"] == "ok" for r in controls),
                    verifier_published=sum(r["status"] == "ok" for r in verify),
                    verifier_attempted=sum(bool(r["expanded_attempted"]) for r in verify),
                    retained_error_km=distribution(r["error_km"] for r in kept),
                    withheld_control_error_km=distribution(r["error_km"] for r in lost),
                    expanded_statuses=dict(
                        Counter(
                            r["expanded_status"] for r in verify if r["expanded_status"] is not None
                        )
                    ),
                    final_withholdings=dict(
                        Counter(r["reason"] for r in verify if r["reason"] is not None)
                    ),
                )
            )
    return summaries


def timing(rows):
    controls = {r["id"]: r for r in rows if r["method"] == STOCK and r["arm"] == "c0"}
    verify = [r for r in rows if r["method"] == VERIFIER and r["arm"] == "c0"]
    out = {}
    for scope in ("all", "expanded", "initial_withheld"):
        group = [
            r
            for r in verify
            if scope == "all" or (r["expanded_attempted"] is (scope == "expanded"))
        ]
        out[scope] = dict(
            scheduled=len(group),
            **{
                name: dict(
                    single=distribution(controls[r["id"]][name] for r in group),
                    verify=distribution(r[name] for r in group),
                    paired_difference=distribution(
                        r[name] - controls[r["id"]][name]
                        for r in group
                        if r[name] is not None and controls[r["id"]][name] is not None
                    ),
                )
                for name in ("worker_cpu_s", "worker_wall_s", "peak_rss_kib", "vm_peak_kib")
            },
            expanded_stage_cpu_s=distribution(r["expanded_stage_cpu_s"] for r in group),
            expanded_stage_wall_s=distribution(r["expanded_stage_wall_s"] for r in group),
        )
    return out


def figures(output, cohort, records, labels, lock):
    queries = []
    for ident in lock["cases"]:
        ref, row = labels[ident], records[VERIFIER][ident]
        bindings = {k: row[k] for k in ("input_sha256", "native_sha256", "catalog_sha256")}
        queries.append(
            dict(
                id=ident,
                condition=ref["condition"],
                recording=ref["recording"],
                truth=ref["truth"],
                bindings=bindings,
            )
        )
    save_json(output / "figure-queries.json", dict(queries=queries))
    files = lock["files"] | {"figure-queries.json": phase.digest(output / "figure-queries.json")}
    save_json(output / "figure-lock.json", dict(cases=lock["cases"], files=files))
    names = {q["condition"] for q in queries}
    exact = all(r.get("observation_sha256") for series in records.values() for r in series.values())
    spec = dict(
        id=f"native_recenter_verify-{cohort}",
        method=VERIFIER,
        scope="transfer",
        title="Recentered verification on roof boundary offers"
        if cohort == "prospective"
        else "Recentered verification on two known false fixes",
        caption="Complete native factors with independently timed single-pass smooth controls.",
        cases=lock["cases"],
        seal="figure-lock.json",
        queries="figure-queries.json",
        condition_labels={k: edge.LABELS[k] for k in edge.CONDITIONS if k in names},
        series=[
            dict(
                key="candidate",
                label="Recentered 50 km verification",
                value=VERIFIER,
                file=f"{VERIFIER}.jsonl.gz",
            ),
            dict(
                key="stock",
                label="Single-pass smooth oscillator",
                value=STOCK,
                file=f"{STOCK}.jsonl.gz",
                match=["input_sha256", "tile"] + (["observation_sha256"] if exact else []),
            ),
        ],
    )
    save_json(output / "figures.json", dict(version=1, charts=[spec]))


def score(output, work):
    cohorts = trial.COHORTS
    if not all((output / scope / "prediction-lock.json").is_file() for scope in cohorts):
        raise ValueError("both replay cohorts must be sealed before geographic scoring")
    with patch.object(edge, "METHODS", METHODS):
        for scope in cohorts:
            folder, run = output / scope, work / scope
            lock, plan, labels, records = edge.validated_rows(folder, run)
            if phase.digest(run / "requests.json") != plan["requests_sha256"]:
                raise ValueError("certified blind requests changed before scoring")
            for name in ("requests.json", "evaluator.json"):
                write(folder / name, (run / name).read_bytes())
            pairs = parity(records)
            rows = edge.score_rows(records, labels)
            pair_rows(rows, records, labels)
            edge.shared.csv_file(folder / "scores.csv", rows)
            repeat = None
            if scope == "diagnosed-stress":
                prior_dir = trial.geom.REPORT / "reserve"
                receipt = phase._read(prior_dir / "prediction-lock.json")
                trial.clock.base.secant_full._verify_files(prior_dir, receipt["files"])
                prior = read_predictions(prior_dir / f"{STOCK}.jsonl.gz")
                repeat = {
                    i: all(prior[i][k] == row[k] for k in ("input_sha256", "observation_sha256"))
                    and prior[i]["result"]["arms"] == row["result"]["arms"]
                    for i, row in records[STOCK].items()
                }
            save_json(
                folder / "summary.json",
                dict(
                    groups=edge.aggregate(rows),
                    paired_conditions=paired_summary(rows, pairs),
                    exact_first_fit=pairs,
                    stress_archive_repeat=repeat,
                    timing=timing(rows),
                    batch_wall_s=lock["wall_s"],
                ),
            )
            figures(folder, scope, records, labels, lock)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=trial.WORK)
    parser.add_argument("--output", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    score(args.output, args.work)


if __name__ == "__main__":
    main()
