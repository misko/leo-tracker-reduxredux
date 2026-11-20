"""Score the sealed rescue split and trace its measurement support through Graph."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import THREAD_ENV, local_output, save_json, write
from ..scoring import ARMS, ROLES
from . import rescue_attribution as trial
from .differential_position_results import GRAPH_PROCESS, graph_members
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .support_cross_results import resources

REPORT = trial.REPORT
PARENT = trial.parent
CONDITIONS = ("stock", "corroborated", "remainder", "union")
MATCH = (
    "tile",
    "catalog_sha256",
    "original_request_sha256",
    "stock_native_sha256",
    "differential_native_sha256",
    "paired_capture_sha256",
)


def rows(folder, seal, file):
    path = trial.sealed(folder, seal, file)
    with gzip.open(path) as stream:
        return list(map(json.loads, stream))


def closed_positions(work, plan):
    new = rows(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    spec = {(r["id"], r["condition"]): r for r in plan["scheduled"]}
    if (
        len(new) != 4
        or {(r["id"], r["condition"]) for r in new} != spec.keys()
        or plan["sources"] != trial.sources()
        or plan["parent_prediction_sha256"] != _sha(PARENT.REPORT / "prediction-lock.json")
        or plan["parent_figure_sha256"] != _sha(PARENT.REPORT / "figure-lock.json")
        or plan["agreement_sha256"] != _sha(trial.agreement.REPORT / "result-lock.json")
    ):
        raise ValueError("sealed source, endpoint or partial-intervention roster differs")
    for row in new:
        ident, condition = row["id"], row["condition"]
        want = spec[ident, condition]
        folder = work / ident / condition
        if any(row[k] != v for k, v in want.items()):
            raise ValueError("partial result differs from its frozen request")
        whole_iq.checked(folder / "service.log", row["log_sha256"])
        if row["terminal"] == "success":
            sample = row["position_resources"]
            if not sample or any(
                sample[edge]["memory.max"] != plan["memory_bytes"]
                or sample[edge]["memory.swap.max"]
                or sample[edge]["memory.swap.current"]
                or sample[edge]["cpus"] != [want["cpu"]]
                for edge in ("start", "end")
            ):
                raise ValueError("successful partial service lacks its physical resource binding")
    cells = {(r["id"], r["condition"]): r for r in new}
    for row in rows(PARENT.REPORT, "figure-lock.json", "positions.jsonl.gz"):
        ident, condition = row["id"], row["condition"]
        if condition in ("stock", "rescue"):
            name = "union" if condition == "rescue" else condition
            want = spec[ident, trial.CHANGES[0]]
            if any(row[field] != want[field] for field in MATCH):
                raise ValueError("archived position differs from the intervention's parent")
            cells[ident, name] = dict(row, condition=name, method=f"rescue_attribution_{name}")
    if set(cells) != {(ident, name) for ident in PARENT.CASES for name in CONDITIONS}:
        raise ValueError("missing or duplicated attribution endpoint")
    return cells


def graph(path, row, config, receiver, cpu):
    whole_iq.checked(path, row["native_sha256"])
    output = subprocess.check_output(
        [
            "nice",
            "-n",
            "10",
            "taskset",
            "-c",
            str(cpu),
            sys.executable,
            "-IB",
            "-c",
            GRAPH_PROCESS,
            receiver,
            str(path),
            row["native_sha256"],
            config["path"],
        ],
        cwd=Path(receiver),
        env={**os.environ, **THREAD_ENV},
        timeout=40,
    )
    sample = json.loads(output)
    metrics = row["result"]["metrics"]
    if "observations" in metrics and (len(sample["winners"]), len(sample["tracks"])) != (
        metrics["observations"],
        metrics["tracks"],
    ):
        raise ValueError("standalone Graph witness differs from the measured fit")
    return sample


def trace_graph(work, raw, union, cells, plan):
    ledger = rows(REPORT, "prediction-lock.json", "packets.jsonl.gz")
    if len({(item["id"], *item["probe"]) for item in ledger}) != len(ledger):
        raise ValueError("gained packet membership must be unique")

    def one(item):
        ident, cpu = item
        case, request = whole_iq.binding(ident)
        paths = {
            name: work / ident / name / "recording/native.json" for name in trial.CHANGES
        } | dict(
            stock=raw / ident / "control/recording/native.json",
            union=union / ident / "rescue/recording/native.json",
        )
        chosen = {tuple(item["probe"]): item for item in ledger if item["id"] == ident}
        added = defaultdict(dict)
        candidates = trial.read(
            whole_iq.checked(paths["union"], cells[ident, "union"]["native_sha256"])
        )
        for packet in candidates["source"]["probes"]:
            member = chosen.get(trial.key(packet))
            if member:
                if trial.digest(packet) != member["replacement_packet_sha256"]:
                    raise ValueError("archived detector packet differs from the split ledger")
                ident_src = (
                    f"{case['session_id']}:{packet['receiver_id']}:{packet['valid_start_counter']}"
                )
                observation = "sha256:" + sha256(ident_src.encode()).hexdigest()
                added[member["group"]][observation] = PARENT.packet(packet)[
                    "fractional_tracking_cfo_hz"
                ]
        if sum(len(group) for group in added.values()) != len(chosen):
            raise ValueError("native gains fail unique observation ID mapping")
        summaries = []
        for name in CONDITIONS:
            sample = graph(
                paths[name],
                cells[ident, name],
                request["job"]["track_config"],
                plan["receiver"],
                cpu,
            )
            winners, points = sample["winners"], graph_members(sample)
            if name == "stock":
                stock, base = winners, points
            groups = trial.CHANGES if name == "union" else (name,) if name in trial.CHANGES else ()
            expected = stock | {k: v for group in groups for k, v in added[group].items()}
            if winners != expected:
                raise ValueError("original stock measurement or rescued CFO changed in Graph")
            summaries.append(
                dict(
                    id=ident,
                    condition=name,
                    native_observations=len(winners),
                    tracks=len(sample["tracks"]),
                    graph_points=len(points),
                    curved_tracks=sum(t["curved"] for t in sample["tracks"]),
                    stock_graph_points_lost=len(base.keys() - points.keys()),
                    **{
                        f"{group}_added_{kind}": count
                        for group in trial.CHANGES
                        for kind, count in (
                            ("winners", len(winners.keys() & added[group].keys())),
                            ("in_graph", len(points.keys() & added[group].keys())),
                            (
                                "in_curved_tracks",
                                sum(
                                    points[k]["curved"] for k in points.keys() & added[group].keys()
                                ),
                            ),
                        )
                    },
                )
            )
        return summaries

    with ThreadPoolExecutor(2) as pool:
        return [row for case in pool.map(one, PARENT.CASES.items()) for row in case]


def contrasts(scores):
    indexed = {(r["id"], r["arm"], r["condition"]): r for r in scores}
    result = []
    for ident in PARENT.CASES:
        for arm in ARMS:
            for metric in ("error_km", "conditional_rf_rms_hz", "observations", "tracks"):
                stock, a, b, both = (indexed[ident, arm, name][metric] for name in CONDITIONS)

                def delta(after, before):
                    return after - before if after is not None and before is not None else None

                left, right = delta(a, stock), delta(both, b)
                result.append(
                    dict(
                        id=ident,
                        arm=arm,
                        metric=metric,
                        corroborated_vs_stock=left,
                        remainder_vs_stock=delta(b, stock),
                        corroborated_given_remainder=right,
                        remainder_given_corroborated=delta(both, a),
                        union_vs_stock=delta(both, stock),
                        interaction=delta(right, left),
                    )
                )
    return result


def measured_resources(cells):
    stock = trial.read(trial.sealed(PARENT.PARENT, "prediction-lock.json", "resources.json"))
    trials = [row for key, row in cells.items() if key[1] != "stock"]
    result = [dict(r, peak_scope="post_detector_cgroup") for r in resources(trials)]
    for ident in PARENT.CASES:
        row = stock[ident]["control"]
        start, finish = row["stages"][-2:]
        result.append(
            dict(
                id=ident,
                condition="stock",
                terminal="success",
                status=cells[ident, "stock"]["result"]["status"],
                support_probes=cells[ident, "stock"]["result"]["metrics"]["observations"],
                cpu=start["cpus"][0],
                cpu_s=(finish["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6,
                wall_s=row["position_s"],
                peak_bytes=row["max_bytes"],
                swap_bytes=row["swap_bytes"],
                peak_scope="whole_IQ_parent_cgroup",
            )
        )
    return result


def figures():
    names = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "scores.csv",
        "effects.csv",
        "graph-support.csv",
        "resources.csv",
        "capture-era-v5.csv",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=list(PARENT.CASES),
            files={name: _sha(REPORT / name) for name in names},
        ),
    )
    charts = []
    for condition, label in (
        ("corroborated", "Capture-corroborated additions"),
        ("remainder", "Remaining differential additions"),
    ):
        charts.append(
            dict(
                id=f"negative-rescue-attribution-{condition}",
                method=f"rescue_attribution_{condition}",
                scope="roof",
                cases="sealed",
                title=f"Negative rescue split · {label}",
                caption=(
                    "Offline attribution on the same two complete recorded IQ inputs. "
                    "Every stock positive stays exact. Stock and union positions are measured "
                    "parent endpoints. Capture-era agreement labels only the added probe packets."
                ),
                seal="figure-lock.json",
                provenance=list(names[1:]),
                series=[
                    dict(
                        file=names[0],
                        key=key,
                        label=text,
                        value=f"rescue_attribution_{name}",
                        native_field="paired_capture_sha256",
                        match=list(MATCH),
                    )
                    for key, text, name in (
                        ("one", label, condition),
                        ("stock", "Stock wide", "stock"),
                        ("one_native_factors", "Complete negative rescue", "union"),
                    )
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=1, charts=charts))


def publish(work, raw, union):
    plan = trial.read(trial.sealed(REPORT, "prediction-lock.json", "plan.json"))
    cells = closed_positions(work, plan)
    graph_rows = trace_graph(work, raw, union, cells, plan)
    _, refs = held_references(None, PARENT.CASES)
    reference = {r["id"]: r for r in refs}
    scores = []
    for (ident, name), row in cells.items():
        for arm in ARMS:
            score = fit(row, reference[ident], arm)
            for role in ROLES:
                baseline = reference[ident]["reference"][role][arm].get("error_km")
                score[f"within_10pct_{role}"] = (
                    baseline is not None
                    and score["error_km"] is not None
                    and score["error_km"] <= 1.1 * baseline
                )
            scores.append(
                dict(
                    score,
                    condition=name,
                    frequency_objective=row["result"]["metrics"].get(f"{arm}_frequency_score"),
                )
            )
    earlier = trial.sealed(PARENT.REPORT, "score-lock.json", "capture-era-v5.csv")
    write(REPORT / "capture-era-v5.csv", earlier.read_bytes())
    write(REPORT / "positions.jsonl.gz", compressed_rows(cells.values()))
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "effects.csv", contrasts(scores))
    csv_file(REPORT / "resources.csv", measured_resources(cells))
    csv_file(REPORT / "graph-support.csv", graph_rows)
    figures()
    names = {
        "figure-lock.json",
        "figures.json",
        *trial.read(REPORT / "figure-lock.json")["files"],
    }
    save_json(
        REPORT / "score-lock.json",
        dict(
            files={name: _sha(REPORT / name) for name in names},
            exporter_sha256=_sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--raw", type=Path, default=PARENT.DEFAULT_RAW)
    parser.add_argument("--union", type=Path, default=trial.PARENT_WORK)
    args = parser.parse_args()
    publish(args.work, args.raw, args.union)
