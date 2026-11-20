"""Score sealed rescue/whole-IQ comparators and audit installed Graph support."""

import argparse
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from statistics import mean

from .. import iq_comparison_results, whole_iq
from ..__main__ import ROOT, THREAD_ENV, local_output, save_json, write
from ..scoring import ARMS, ROLES
from .differential_position_results import GRAPH_PROCESS, graph_members
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit, sealed
from .negative_rescue_trial import (
    CASES,
    DEFAULT_RAW,
    METHOD,
    PARENT,
    REPORT,
    combine,
    compare_raw,
    raw_pair,
    read,
)
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .support_cross_results import resources


def runtime_model(rows, audit):
    costs = []
    for ident in CASES:
        group = [r for r in rows if r["id"] == ident]
        selector = audit[ident]["selector_cpu_s"]
        if len(group) != audit[ident]["raw"]["valid"]:
            raise ValueError("clock ledger does not cover every admitted stereo call")
        calls = [r for r in group if r["second_call"]]
        serial = [r["stock_wall_s"] + r["second_call"] * r["differential_wall_s"] for r in group]
        baseline = sum(r["stock_cpu_s"] for r in group)
        addition = sum(r["differential_cpu_s"] for r in calls)
        costs.append(
            dict(
                id=ident,
                admitted_visits=len(group),
                second_calls=len(calls),
                fraction_second=len(calls) / len(group),
                measured_stock_total_cpu_s=baseline,
                measured_unconditional_total_cpu_s=sum(r["differential_cpu_s"] for r in group),
                modeled_extra_cpu_s=addition,
                measured_selector_cpu_s=selector,
                modeled_rescue_cpu_s=baseline + addition + selector,
                measured_stock_mean_cpu_ms=baseline * 1000 / len(group),
                measured_unconditional_mean_cpu_ms=mean(
                    r["differential_cpu_s"] * 1000 for r in group
                ),
                modeled_rescue_mean_cpu_ms=(baseline + addition + selector) * 1000 / len(group),
                modeled_serial_mean_wall_ms=mean(v * 1000 for v in serial),
                measured_stock_wall_le_20ms=sum(r["stock_wall_s"] <= 0.020 for r in group),
                measured_unconditional_wall_le_20ms=sum(
                    r["differential_wall_s"] <= 0.020 for r in group
                ),
                modeled_serial_wall_le_20ms=sum(v <= 0.020 for v in serial),
            )
        )
    return costs


def controls(plan):
    source = read(PARENT / "source-lock.json")
    if _sha(PARENT / "source-lock.json") != plan["parent_source_lock_sha256"]:
        raise ValueError("whole-IQ comparators differ from the raw input plan")
    parents = sealed(PARENT, "prediction-lock.json", "positions.jsonl.gz")
    science = []
    for spec in plan["scheduled"]:
        ident = spec["id"]
        for role, name in (("control", "stock"), ("candidate", "unconditional")):
            method = iq_comparison_results.method(source["spec"]["id"], role)
            (row,) = [r for r in parents if (r["id"], r["method"]) == (ident, method)]
            if (
                any(
                    row[k] != spec[k]
                    for k in (
                        "tile",
                        "catalog_sha256",
                        "original_request_sha256",
                        "paired_capture_sha256",
                    )
                )
                or row["native_sha256"] != spec["raw_parents"][role]["native_sha256"]
            ):
                raise ValueError("reference position was fed different native factors or request")
            science.append(
                dict(
                    row,
                    condition=name,
                    method=METHOD + "_" + name,
                    stock_native_sha256=spec["stock_native_sha256"],
                    differential_native_sha256=spec["differential_native_sha256"],
                )
            )
    return science


def installed_graph(work, raw, plan, positions, audit):
    data = {(r["id"], r["condition"]): r for r in positions}
    graph_records = []
    for ident, cpu in CASES.items():
        case, request = whole_iq.binding(ident)
        config = request["job"]["track_config"]
        whole_iq.checked(Path(config["path"]), config["sha256"])
        paths = {
            "stock": raw / ident / "control/recording/native.json",
            "unconditional": raw / ident / "candidate/recording/native.json",
            "rescue": work / ident / "rescue/recording/native.json",
        }
        built = {}
        for condition, path in paths.items():
            position = data[ident, condition]
            digest = position["native_sha256"]
            request_digest = plan["scheduled"][list(CASES).index(ident)]["original_request_sha256"]
            if request_digest != case["request"]["sha256"]:
                raise ValueError("separate Graph support uses an unmatched original request")
            command = [
                "taskset",
                "-c",
                str(cpu),
                sys.executable,
                "-IB",
                "-c",
                GRAPH_PROCESS,
                plan["receiver"],
                str(path),
                digest,
                config["path"],
            ]
            science = json.loads(
                subprocess.check_output(command, env={**os.environ, **THREAD_ENV}, timeout=40)
            )
            metrics = position["result"]["metrics"]
            if "observations" in metrics and (len(science["winners"]), len(science["tracks"])) != (
                metrics["observations"],
                metrics["tracks"],
            ):
                raise ValueError(
                    "independent Graph preparation did not reproduce actual solver counters"
                )
            built[condition] = science
        base, diff, rescue = (built[k]["winners"] for k in paths)
        gained = set(rescue) - base.keys()
        new_ids = {
            "sha256:"
            + sha256(
                f"{case['session_id']}:{g['receiver']}:{g['counter']}".encode()
            ).hexdigest(): g["cfo_hz"]
            for g in audit[ident]["gain"]
        }
        if gained != new_ids.keys() or any(rescue.get(k) != v for k, v in (base | new_ids).items()):
            raise ValueError(
                "installed prep dropped or altered a stock or rescue receiver measurement"
            )
        original_graph = graph_members(built["stock"])
        for condition, block in built.items():
            members = graph_members(block)
            winners = block["winners"]
            graph_records.append(
                dict(
                    id=ident,
                    condition=condition,
                    native_positive=len(winners),
                    graph_tracks=len(block["tracks"]),
                    original_positive_lost=len(base.keys() - winners.keys()),
                    original_positive_cfo_changed=sum(
                        winners[k] != base[k] for k in base.keys() & winners.keys()
                    ),
                    introduced_observations=len(winners.keys() - base.keys()),
                    rescue_observations_in_graph=len(gained & members.keys()),
                    original_graph_points_lost=len(original_graph.keys() - members.keys()),
                    graph_points=len(members),
                    unconditional_lost_stock=len(base.keys() - diff.keys()),
                    unconditional_changed_stock_cfo=sum(
                        diff[k] != base[k] for k in base.keys() & diff.keys()
                    ),
                )
            )
    csv_file(REPORT / "graph-support.csv", graph_records)


def position_figure():
    provenance = [
        "prediction-lock.json",
        "probe-audit.json",
        "online-work.csv",
        "graph-support.csv",
        "scores.csv",
    ]
    names = ("positions.jsonl.gz", *provenance)
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(CASES), files={k: _sha(REPORT / k) for k in names}),
    )

    def series(key, label, value):
        return dict(
            key=key,
            label=label,
            value=value,
            file="positions.jsonl.gz",
            native_field="paired_capture_sha256",
            match=[
                "tile",
                "catalog_sha256",
                "original_request_sha256",
                "stock_native_sha256",
                "differential_native_sha256",
            ],
        )

    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="whole-iq-negative-rescue",
                    method=METHOD,
                    scope="roof",
                    cases="sealed",
                    title="Keep stock admissions and rescue only negative probes",
                    caption=(
                        "Both complete detector passes used the same saved IQ. The rescue keeps "
                        "every ordinary positive packet and adopts differential additions. "
                        "The same installed solver fits both original roof recordings."
                    ),
                    seal="figure-lock.json",
                    provenance=provenance,
                    series=[
                        series("one", "Negative-only rescue", METHOD),
                        series("stock", "Complete stock wide", METHOD + "_stock"),
                        series(
                            "one_native_factors",
                            "Unconditional differential",
                            METHOD + "_unconditional",
                        ),
                    ],
                )
            ],
        ),
    )


def verify_sources(raw, plan, audit, timings):
    changes = {
        name: dict(sealed=digest, current=observed)
        for name, digest in plan["sources"].items()
        if (observed := _sha(ROOT / name)) != digest
    }
    external = "tools/pipeline_eval/qualification/frontier_whole_replay_results.py"
    if changes.keys() - {external}:
        raise ValueError("a frozen rescue source changed")
    if changes:
        source = read(whole_iq.checked(raw / "source-lock.json", plan["parent_source_lock_sha256"]))
        clock_rows = []
        for spec in plan["scheduled"]:
            ident = spec["id"]
            _, parent = whole_iq.binding(ident)
            payloads, branches, pinned = raw_pair(
                raw / ident, source, parent, source["cases"][ident]
            )
            _, packets, gains, _ = combine(*payloads)
            raw_counts, clocks = compare_raw(payloads, branches, raw / ident)
            if pinned != spec["raw_parents"] or (packets, gains, raw_counts) != tuple(
                audit[ident][k] for k in ("packets", "gain", "raw")
            ):
                raise ValueError("the changed report writer did not reproduce the sealed raw audit")
            clock_rows.extend(dict(id=ident, **row) for row in clocks)
        if clock_rows != timings or _sha(ROOT / external) != changes[external]["current"]:
            raise ValueError("raw-timing replay is not identical to the sealed timing ledger")
    save_json(
        REPORT / "source-audit.json",
        dict(report_writer_changes=changes, exact_raw_audit_reproduced=bool(changes)),
    )


def publish(work, raw):
    rows = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    plan = read(REPORT / "plan.json")
    if len(rows) != len(CASES) or {r["id"] for r in rows} != set(CASES):
        raise ValueError("the two preregistered rescue attempts are required")
    audit = {r["id"]: r for r in read(REPORT / "probe-audit.json")}
    timings = sealed(REPORT, "prediction-lock.json", "raw-clock-ledger.jsonl.gz")
    verify_sources(raw, plan, audit, timings)
    combined = rows + controls(plan)
    installed_graph(work, raw, plan, combined, audit)
    csv_file(REPORT / "online-work.csv", runtime_model(timings, audit))
    csv_file(REPORT / "resources.csv", resources(rows))
    _, refs = held_references(None, CASES)
    reference = {r["id"]: r for r in refs}
    scores, earlier = [], []
    for row in combined:
        ident = row["id"]
        for arm in ARMS:
            score = fit(row, reference[ident], arm)
            orig = reference[ident]["reference"]["baseline"][arm]["error_km"]
            scores.append(
                dict(
                    score,
                    condition=row["condition"],
                    original_v5_error_km=orig,
                    within_10pct_original=score["error_km"] is not None
                    and score["error_km"] <= 1.1 * orig,
                )
            )
    for ident, ref in reference.items():
        for arm in ARMS:
            for method in ROLES:
                values = ref["reference"][method][arm]
                earlier.append(
                    dict(
                        id=ident,
                        arm=arm,
                        method=method,
                        **{k: values.get(k) for k in ("status", "error_km", "rf_rms_hz", "wall_s")},
                    )
                )
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "capture-era-v5.csv", earlier)
    write(REPORT / "positions.jsonl.gz", compressed_rows(combined))
    position_figure()
    files = (
        "prediction-lock.json",
        "scores.csv",
        "positions.jsonl.gz",
        "graph-support.csv",
        "online-work.csv",
        "resources.csv",
        "capture-era-v5.csv",
        "source-audit.json",
        "figures.json",
        "figure-lock.json",
    )
    save_json(
        REPORT / "score-lock.json",
        dict(
            files={f: _sha(REPORT / f) for f in files},
            whole_iq_prediction_lock_sha256=_sha(PARENT / "prediction-lock.json"),
            sources_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--raw", type=local_output, default=DEFAULT_RAW)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work, args.raw)
    if args.plot:
        from .screening_figures import generate

        generate(args.plot, evidence=REPORT)
