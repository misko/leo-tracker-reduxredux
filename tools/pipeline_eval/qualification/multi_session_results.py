"""Seal stationary location decisions, then score independently supplied survey labels."""

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .. import corpus, figure_books, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import compact_tile_interior
from ..variants import multi_session as solver
from . import multi_session_trial as trial
from .full_v5_check import _sha
from .prefix_figures import csv_file

DECISIONS = "blind-decisions.json"
DECISION_LOCK = "decision-lock.json"
POSITIONS = "positions.jsonl.gz"
CONDITIONS = dict(
    containing="Original containing offer",
    near_missing="Near missing offer",
    far_missing="Far missing offer",
)
BASE_METHODS = dict(
    all_sessions="All sessions",
    early_group="Early group",
    late_group="Later group",
    session_1="First session",
    time_shuffle="73 s time shuffle",
    center="No data, offer center",
)
BOUNDARY = "Archived native GLRT and causal TLEs through stationary regional likelihood"


def load_rows(report):
    seal = whole_iq.read(report / trial.LOCK)
    for name, digest in seal["files"].items():
        whole_iq.checked(report / name, digest)
    plan = whole_iq.read(report / trial.PLAN)
    rows = list(
        map(json.loads, gzip.decompress((report / trial.PROFILES).read_bytes()).splitlines())
    )
    if [r["id"] for r in rows] != seal["cases"]:
        raise ValueError("stationary session output differs from the sealed roster")
    for case, row in zip(plan["candidates"], rows, strict=True):
        if row["id"] != case["id"] or any(row[k] != v for k, v in case.items()):
            raise ValueError("stationary session output changed its authenticated input")
    return rows


def split_scores(rows, group=None, *, mode=0, field="held"):
    selected = [
        r["profile"] for r in rows if r["status"] == "ok" and (group is None or r["group"] == group)
    ]
    if not selected:
        return None
    raw = solver.aggregate(selected, field, mode)
    epochs = sum(profile[f"{field}_epochs"] for profile in selected)
    return raw / epochs


def site_choice(train, candidates, center, offsets):
    if train is None:
        return None
    return max(
        candidates, key=lambda cell: (train[cell], -np.linalg.norm(offsets[center] - offsets[cell]))
    )


def evidence(hypothesis, score, offsets, allowed):
    if hypothesis is None or score is None:
        return dict(score=None, lead=None, rank=None, rival=None, winner_outside=None)
    separated = np.flatnonzero(np.linalg.norm(offsets - offsets[hypothesis], axis=1) >= 10)
    rival = separated[np.argmax(score[separated])]
    return dict(
        score=float(score[hypothesis]),
        lead=float(score[hypothesis] - score[rival]),
        rank=1 + int(np.sum(score > score[hypothesis])),
        rival=offsets[rival].tolist(),
        winner_outside=int(np.argmax(score)) not in allowed,
    )


def stationary(rows):
    """Select on training only. Report spatial preference against common held evidence."""
    centers = {tuple(row["tile"]["center"]) for row in rows}
    if len(centers) != 1 or set(r["group"] for r in rows) != {"early", "late"}:
        raise ValueError("a stationary cohort requires a common public origin and two time groups")
    center = list(centers.pop())
    sites, offers = solver.design(center)
    offsets = np.array(list(sites))
    indexes = {cell: i for i, cell in enumerate(sites)}
    successful = [r for r in rows if r["status"] == "ok"]
    if any([tuple(cell) for cell in r["profile"]["cells"]] != list(sites) for r in successful):
        raise ValueError("session likelihood cells differ from the fixed geodetic bank")
    all_train = split_scores(rows, field="train")
    all_held = split_scores(rows)
    early = split_scores(rows, "early", field="train")
    late = split_scores(rows, "late", field="train")
    early_held, late_held = split_scores(rows, "early"), split_scores(rows, "late")
    null_train = split_scores(rows, mode=1, field="train")
    null_held = split_scores(rows, mode=1)
    variants = dict(
        all_sessions=(all_train, len(rows)),
        early_group=(early, sum(r["group"] == "early" for r in rows)),
        late_group=(late, sum(r["group"] == "late" for r in rows)),
        time_shuffle=(null_train, len(rows)),
        center=(np.zeros(len(sites)), 0),
    )
    for i, row in enumerate(rows, 1):
        variants[f"session_{i}"] = (split_scores([row], field="train"), 1)
        variants[f"prefix_{i}"] = (split_scores(rows[:i], field="train"), i)
    results = []
    for offer, policy in offers.items():
        allowed = [indexes[cell] for cell in policy["points"]]
        origin = indexes[solver.OFFERS[offer]]
        proposals = [
            (method, site_choice(train, allowed, origin, offsets), train, sessions)
            for method, (train, sessions) in variants.items()
        ]
        for method, selected, train, sessions in proposals:
            held = evidence(selected, all_held, offsets, allowed)
            forward = evidence(selected, late_held, offsets, allowed)
            backward = evidence(selected, early_held, offsets, allowed)
            rank_training = evidence(selected, train, offsets, allowed)
            point = list(sites[tuple(offsets[selected])]) if selected is not None else None
            time_lead = (
                float(all_held[selected] - null_held[selected])
                if selected is not None and all_held is not None and null_held is not None
                else None
            )
            center_lead = (
                float(all_held[selected] - all_held[origin])
                if selected is not None and all_held is not None
                else None
            )
            if selected is None:
                status, reason = "unavailable", "no_successful_training_likelihood"
            elif method != "all_sessions":
                status, reason = "withheld", "experimental_comparison"
            elif (
                len(successful) == len(rows)
                and forward["lead"] is not None
                and forward["lead"] > 0
                and held["lead"] is not None
                and held["lead"] >= 0.04
                and time_lead is not None
                and time_lead >= 0.075
            ):
                status, reason = "ok", None
            else:
                status, reason = "withheld", "insufficient_repeated_spatial_evidence"
            result = dict(
                status=status,
                reason=reason,
                boundary=BOUNDARY,
                metrics=dict(
                    position_attempted=selected is not None,
                    sessions=sessions,
                    selected_offset_km=offsets[selected].tolist() if selected is not None else None,
                    training=rank_training,
                    held=held,
                    early_held=backward,
                    later_held=forward,
                    held_time_shuffle_lead=time_lead,
                    held_center_lead=center_lead,
                ),
                arms={
                    arm: dict(
                        latlon=point if status == "ok" else None,
                        forced_latlon=point if status != "ok" else None,
                    )
                    for arm in ARMS
                },
            )
            validate_result(result)
            results.append(
                dict(
                    offer=offer,
                    method=method,
                    tile=dict(center=policy["center"], width_km=25),
                    result=result,
                )
            )
    return results


def decide(report):
    if (report / DECISION_LOCK).exists():
        raise FileExistsError("location decisions are already sealed")
    rows = load_rows(report)
    decisions = stationary(rows)
    save_json(report / DECISIONS, decisions)
    names = (trial.LOCK, trial.PLAN, trial.PROFILES, DECISIONS)
    save_json(
        report / DECISION_LOCK,
        dict(
            files={name: _sha(report / name) for name in names},
            scorer_sha256=_sha(Path(__file__)),
        ),
    )


def after_lock(report):
    receipt = whole_iq.read(report / DECISION_LOCK)
    for name, digest in receipt["files"].items():
        whole_iq.checked(report / name, digest)
    rows = load_rows(report)
    decisions = whole_iq.read(report / DECISIONS)
    return rows, decisions


def references(rows):
    ids = {row["id"] for row in rows}
    refs = {
        row["id"]: row
        for panel in ("roof16", "ds26-all159")
        for row in corpus.references(panel)
        if row["id"] in ids
    }
    if set(refs) != ids:
        raise ValueError("original v5 and surveyed roof references do not cover the roster")
    truth = refs[rows[0]["id"]]["truth"]
    if any(distance_km(truth, ref["truth"]) > 0.01 for ref in refs.values()):
        raise ValueError("more than one survey site in the measured roof cohort")
    return truth, refs


def score_row(row, truth, case_refs):
    result = row["result"]
    pair = result["arms"]
    if pair["c0"] != pair["fitted_c"]:
        raise ValueError("a time difference in the same RF lane cannot identify fixed c")
    endpoint = pair["c0"]
    score = dict(
        id=row["id"],
        offer=row["offer"],
        method=row["method"],
        status=result["status"],
        reason=result["reason"],
        sessions=result["metrics"]["sessions"],
        site_offset_km=result["metrics"]["selected_offset_km"],
        truth_margin_km=compact_tile_interior.margin(truth, row["tile"]),
        geographic_error_km=distance_km(endpoint["latlon"], truth),
        forced_error_km=distance_km(endpoint["forced_latlon"], truth),
    )
    for name in ("training", "held", "early_held", "later_held"):
        for field, value in result["metrics"][name].items():
            score[f"{name}_{field}"] = value
    for name in ("held_time_shuffle_lead", "held_center_lead"):
        score[name] = result["metrics"][name]
    if case_refs is not None and row["method"].startswith("session_"):
        i = int(row["method"].split("_")[-1]) - 1
        ref = case_refs[i]["reference"].get("baseline", {})
        score["original_no_repair_c0_km"] = ref.get("c0", {}).get("error_km")
        score["original_no_repair_fitted_c_km"] = ref.get("fitted_c", {}).get("error_km")
    else:
        score["original_no_repair_c0_km"] = score["original_no_repair_fitted_c_km"] = None
    return score


def descriptors(report, queries):
    queries_file, seal = "queries.json", "figure-lock.json"
    save_json(report / queries_file, dict(queries=queries))
    provenance = ("scores.csv", "summary.json", DECISION_LOCK)
    cases = [q["id"] for q in queries]
    names = (POSITIONS, queries_file, *provenance)
    save_json(report / seal, dict(cases=cases, files={name: _sha(report / name) for name in names}))
    charts = []
    for name, title, pairs in (
        (
            "stationary-sessions",
            "Stationary position across six roof recordings",
            (
                ("candidate", "all_sessions"),
                ("stock", "early_group"),
                ("one", "late_group"),
                ("four", "session_1"),
            ),
        ),
        (
            "stationary-controls",
            "Stationary likelihood against time shuffle and no data",
            (
                ("candidate", "all_sessions"),
                ("stock", "time_shuffle"),
                ("one", "center"),
            ),
        ),
    ):
        charts.append(
            dict(
                id=name,
                method=name,
                scope="transfer",
                cases="sealed",
                seal=seal,
                provenance=provenance,
                queries=queries_file,
                condition_labels=CONDITIONS,
                title=title,
                caption=(
                    "Anonymous GLRT peak pairs, causal orbits and independent clocks. "
                    "The stationary prior spans six acquisitions at one roof. "
                    "Differences within each RF lane cancel fixed calibration exactly."
                ),
                series=[
                    dict(
                        file=POSITIONS,
                        key=key,
                        value=method,
                        label=BASE_METHODS[method],
                        forced_label=BASE_METHODS[method] + " (diagnostic)",
                    )
                    for key, method in pairs
                ],
            )
        )
    save_json(report / "figures.json", dict(version=2, charts=charts))


def support_figure(report, scores, rows):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 3, figsize=(12.8, 4.4), sharey=True)
    early = sum(r["group"] == "early" for r in rows)
    for ax, (offer, label) in zip(axes, CONDITIONS.items(), strict=True):
        selected = {r["method"]: r for r in scores if r["offer"] == offer}
        steps = np.arange(1, len(rows) + 1)
        prefixes = [selected[f"prefix_{i}"] for i in steps]
        singles = [selected[f"session_{i}"] for i in steps]
        ax.axhline(0, color="#4b5563", linewidth=0.8)
        ax.axhline(0.04, color="#9ca3af", linestyle=":", linewidth=1)
        ax.axvline(early + 0.5, color="#9ca3af", linestyle="--", linewidth=1)
        ax.plot(
            steps,
            [r["held_lead"] for r in prefixes],
            "o-",
            color="#007f73",
            label="Cumulative, all held blocks",
        )
        ax.plot(
            steps,
            [r["held_lead"] for r in singles],
            "s--",
            color="#aa6418",
            alpha=0.8,
            label="Session alone, all held blocks",
        )
        ax.plot(
            steps[:early],
            [r["later_held_lead"] for r in prefixes[:early]],
            "D-",
            color="#5751a9",
            label="Early only, later held blocks",
        )
        ax.set(title=label, xlabel="Chronological acquisition number", xticks=steps)
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Mean held log-score lead over best rival ≥10 km away")
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, labels, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 0.015))
    figure.suptitle("Does geographic support accumulate across independent acquisitions?")
    figure.tight_layout(rect=(0, 0.10, 1, 0.94))
    figure.savefig(report / "stationary-support.png", dpi=175)
    figure.savefig(report / "stationary-support.pdf")
    plt.close(figure)


def score(report, *, render):
    rows, decisions = after_lock(report)
    truth, refs = references(rows)
    token = _sha(report / trial.PROFILES)
    chart_rows, scores, queries, seen = [], [], [], set()
    for row in decisions:
        label = row["offer"]
        ident = f"roof-{label}"
        bindings = dict(input_sha256=token, tile=row["tile"])
        if label not in seen:
            seen.add(label)
            margin = compact_tile_interior.margin(truth, row["tile"])
            if (margin >= 0) != (label == "containing"):
                raise ValueError("the offer classification differs from its surveyed geometry")
            queries.append(
                dict(
                    id=ident, condition=label, recording="one-roof", truth=truth, bindings=bindings
                )
            )
        chart_rows.append(dict(id=ident, method=row["method"], result=row["result"], **bindings))
        scores.append(score_row(dict(row, id=ident), truth, [refs[r["id"]] for r in rows]))
    csv_file(report / "scores.csv", scores)
    write(
        report / POSITIONS, gzip.compress(b"".join(encoded(r) + b"\n" for r in chart_rows), mtime=0)
    )
    successes = [row for row in rows if row["status"] == "ok"]
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row["id"])
    info = dict(
        groups=groups,
        sessions_attempted=len(rows),
        sessions_with_profiles=len(successes),
        accumulated_capture_s=sum(row["capture_s"] for row in rows),
        elapsed_span_s=(rows[-1]["cutoff_utc_ns"] - rows[0]["cutoff_utc_ns"]) / trial.NANO
        + rows[-1]["capture_s"],
        cpu_s=distribution(row.get("cpu_s") for row in rows),
        worker_wall_s=distribution(row.get("worker_wall_s") for row in rows),
        peak_rss_mib=max((row.get("peak_rss_kib", 0) for row in rows), default=0) / 1024,
        statuses={row["id"]: row["status"] for row in rows},
        total_numerical_cpu_s=sum(row["cpu_s"] for row in successes),
        total_exact_rate_evaluations=sum(
            row["profile"]["exact_rate_evaluations"] for row in successes
        ),
        comparisons=[r for r in scores if r["method"] in BASE_METHODS],
    )
    save_json(report / "summary.json", info)
    descriptors(report, queries)
    support_figure(report, scores, rows)
    paths = (
        POSITIONS,
        "figures.json",
        "figure-lock.json",
        "summary.json",
        "scores.csv",
        "stationary-support.png",
        "stationary-support.pdf",
        DECISION_LOCK,
    )
    if render:
        figure_books.generate(
            report / "charts",
            ARMS,
            panel="screening",
            evidence=report,
            methods=("stationary-sessions", "stationary-controls"),
        )
        paths += ("charts/manifest.json",)
    save_json(
        report / "score-lock.json",
        dict(
            files={name: _sha(report / name) for name in paths},
            scorer_sha256=_sha(Path(__file__)),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("decide", "score"))
    parser.add_argument("--report", type=local_output, default=trial.OUT)
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    if args.action == "decide":
        decide(args.report)
    else:
        score(args.report, render=args.render)


if __name__ == "__main__":
    main()
