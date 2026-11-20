"""Seal, score and plot the fresh aligned late-preflight cost pairs."""

import argparse
from collections import Counter
from pathlib import Path

from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import full_receiver_comparison as authority
from . import late_cost_trial as trial
from . import late_preflight_live_results as live
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

CHART = "late-cost-roof"
POSITIONS = "positions.jsonl.gz"
ATTEMPTS = "attempts.jsonl.gz"
PAIR_FILE = "pairs.json"
TIMING_PLOT = "timing.png"
LATE = ("ranking", "admission", "final")
MATCH = (*trial.archive.MATCH, "input_sha256", "scientific_request_sha256")


def record(work, ident, method, binding, schedule):
    path = work / ident / method / "attempt.json"
    expected = dict(
        binding,
        method=method,
        cpu=schedule["cpu"],
        branch=schedule["branch"],
        order=schedule["methods"].index(method),
    )
    if not path.exists():
        result = dict(
            trial.nonresult("planned worker did not write an attempt receipt"), status="missing"
        )
        return dict(expected, resources={}, result=result, attempt_sha256=None)
    row = authority.read(path)
    authority.require_fields(row, expected)
    if row["result"]["status"] == "ok":
        authority.require_fields(
            row["request_proof"],
            dict(
                scientific_request_sha256=binding["scientific_request_sha256"],
                worker_request_sha256=authority.sha(path.with_name("request.json")),
            ),
        )
        raw = authority.read(path.with_name("result.json"))
        metrics = dict(raw["metrics"], candidate_s=row["result"]["metrics"]["candidate_s"])
        if dict(raw, metrics=metrics) != row["result"]:
            raise ValueError(f"{ident} worker result changed after its complete paired attempt")
        row["worker_result_sha256"] = authority.sha(path.with_name("result.json"))
    validate_result(row["result"])
    return dict(row, attempt_sha256=authority.sha(path))


def detail(row):
    result = row["result"]
    metrics = result["metrics"]
    timings = metrics.get("paired_cost")
    data = dict(
        status=result["status"],
        attempt_state=(
            "not_started"
            if result["status"] == "timed_out" and row.get("cap_s") == 0
            else result["status"]
        ),
        reason=result.get("reason"),
        order=row["order"],
        supervisor=row["resources"],
        guard=metrics.get(trial.GUARD),
        decisions={k: metrics.get(k) for k in live.DECISIONS},
        wall_cap_s=row.get("cap_s"),
    )
    if timings:
        data.update(
            worker=timings["worker"],
            upstream=timings["upstream"],
            late=timings["late"]["stages"],
            work=timings["late"]["work"],
        )
    return data


def compare_pair(stock, guarded):
    control, candidate = map(detail, (stock, guarded))
    pair = dict(
        id=stock["id"],
        cpu=stock["cpu"],
        branch=stock["branch"],
        control=control,
        guarded=candidate,
        complete=False,
    )
    if control["status"] != "ok" or candidate["status"] != "ok":
        return pair
    pair["complete"] = True
    before, after = stock["result"], guarded["result"]
    arm = live.compare(after, before)
    for name, comparison in arm.items():
        for metric in ("associated_observations", "frequency_score"):
            old, new = (r["metrics"].get(f"{name}_{metric}") for r in (before, after))
            comparison[f"{metric}_delta"] = None if old is None or new is None else new - old
    pair["arms"] = arm
    pair["savings_s"] = {}
    for key in ("wall_s", "cpu_s"):
        pair["savings_s"][key] = dict(
            full_worker=control["worker"][key] - candidate["worker"][key],
            full_launcher=control["supervisor"][key] - candidate["supervisor"][key],
            late=sum(control["late"][name][key] - candidate["late"][name][key] for name in LATE)
            - candidate["upstream"][trial.GUARD][key],
        )
    return pair


def timing_chart(pairs, path):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    palette = dict(
        other="#758997", ranking="#5397a6", admission="#bd6d32", final="#7968a1", guard="#202c34"
    )
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 6.6))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.87, bottom=0.14, hspace=0.44, wspace=0.23)
    fig.suptitle("Late RF preflight on fresh same-core pairs", fontsize=19, weight="bold")
    names = {
        "other": "All other worker stages",
        "ranking": "Family ranking",
        "admission": "Candidate admission",
        "final": "Final fit or fallback",
        "guard": "RF preflight",
    }
    x = list(range(len(pairs)))
    for index, key in enumerate(("cpu_s", "wall_s")):
        for panel in range(2):
            ax = axes[panel, index]
            ax.set_title(
                ("Complete worker" if panel == 0 else "Late decision stages")
                + (" · CPU" if index == 0 else " · wall"),
                loc="left",
                fontsize=13,
            )
            ax.set_ylabel("Seconds")
            ax.set_xticks(x, [r["id"] for r in pairs])
            ax.grid(axis="y", alpha=0.25)
            ax.set_axisbelow(True)
            for pos, pair in enumerate(pairs):
                for side, caption, offset in (
                    ("control", "Aligned", -0.19),
                    ("guarded", "Guarded", 0.19),
                ):
                    row = pair[side]
                    if row["status"] != "ok":
                        ax.text(
                            pos + offset,
                            0.02,
                            row["attempt_state"].replace("_", " "),
                            rotation=90,
                            ha="center",
                            transform=ax.get_xaxis_transform(),
                            color="#662d21",
                            size=8,
                        )
                        continue
                    parts = {stage: row["late"][stage][key] for stage in LATE}
                    parts["guard"] = row["upstream"].get(trial.GUARD, {}).get(key, 0)
                    other = max(0, row["worker"][key] - sum(parts.values()))
                    plotted = (dict(other=other) | parts) if panel == 0 else parts
                    bottom = 0
                    for stage, value in plotted.items():
                        ax.bar(
                            pos + offset,
                            value,
                            bottom=bottom,
                            width=0.34,
                            color=palette[stage],
                            zorder=3,
                        )
                        bottom += value
                    ax.annotate(
                        caption,
                        (pos + offset, bottom),
                        xytext=(0, 4),
                        textcoords="offset points",
                        ha="center",
                        fontsize=8,
                    )
            ax.margins(y=0.15)
            ax.set_xlim(-0.55, len(pairs) - 0.45)
    handles = [Patch(color=color, label=names[key]) for key, color in palette.items()]
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, fontsize=9)
    fig.savefig(path, dpi=190)
    plt.close(fig)


def amended_records(work, plan, alternate):
    if alternate is None:
        return None, []
    amendment = authority.read(alternate / "affinity-amendment.json")
    ident = amendment["id"]
    original = plan["schedule"][ident]
    revision = amendment["amended"]
    if (
        amendment["original_plan_sha256"] != authority.sha(work / "plan.json")
        or amendment["original"] != original
        or revision != dict(original, cpu=7)
        or revision["cpu"] == original["cpu"]
    ):
        raise ValueError("affinity amendment changed more than the designated same-core pin")
    updated = dict(plan, schedule=plan["schedule"] | {ident: revision})
    if updated != authority.read(alternate / "plan.json"):
        raise ValueError("amended schedule changed the locked requests, order or deadline")
    rows = [
        record(alternate, ident, method, plan["bindings"][ident], revision)
        for method in (trial.STOCK, trial.CANDIDATE)
    ]
    return amendment, rows


def publish(work, out, alternate=None):
    _, expected = trial.source_inputs()
    plan = authority.read(work / "plan.json")
    authority.require_fields(plan, expected)
    run = authority.read(work / "run-receipt.json")
    cases = list(plan["schedule"])
    original_rows = [
        record(work, ident, method, plan["bindings"][ident], plan["schedule"][ident])
        for ident in cases
        for method in (trial.STOCK, trial.CANDIDATE)
    ]
    amendment, extra = amended_records(work, plan, alternate)
    rows = list(original_rows)
    extra_pair = compare_pair(*extra) if extra else None
    if extra_pair and extra_pair["complete"]:
        index = next(i for i, row in enumerate(rows) if row["id"] == extra_pair["id"])
        if not compare_pair(*rows[index : index + 2])["complete"]:
            rows[index : index + 2] = extra
    refs, _ = _frozen_roof()
    pairs = [compare_pair(rows[i], rows[i + 1]) for i in range(0, len(rows), 2)]
    score = []
    for row in rows:
        ref = refs[row["id"]]
        for arm in ARMS:
            result = row["result"]
            point = result["arms"][arm]["latlon"]
            score.append(
                dict(
                    id=row["id"],
                    method=row["method"],
                    branch=row["branch"],
                    status=result["status"],
                    arm=arm,
                    error_km=distance_km(point, ref["truth"]),
                    conditional_rms_hz=result["metrics"].get(f"{arm}_conditional_rms_hz"),
                    **{
                        f"v5_{k}_error_km": ref["reference"][k][arm]["error_km"]
                        for k in authority.ROLES
                    },
                )
            )
    initial = [r for r in pairs if r["complete"]]
    summary = dict(
        cases=cases,
        completed_pairs=len(initial),
        attempts=Counter(r["result"]["status"] for r in rows),
        original_attempts=Counter(r["result"]["status"] for r in original_rows),
        amended_attempts=Counter(r["result"]["status"] for r in extra),
        original_attempt_states=Counter(detail(r)["attempt_state"] for r in original_rows),
        amended_attempt_states=Counter(detail(r)["attempt_state"] for r in extra),
        measured_bypasses=sum(not r["guarded"]["guard"]["run"] for r in initial),
        paired_by_observed_branch={
            branch: {
                key: distribution(
                    r["savings_s"][key]["full_worker"]
                    for r in initial
                    if r["guarded"]["guard"]["run"] is runs
                )
                for key in ("cpu_s", "wall_s")
            }
            for branch, runs in (("bypass", False), ("retained", True))
        },
        full_worker_savings_s={
            key: distribution(r["savings_s"][key]["full_worker"] for r in initial)
            for key in ("cpu_s", "wall_s")
        },
        stage_savings_s={
            key: distribution(r["savings_s"][key]["late"] for r in initial)
            for key in ("cpu_s", "wall_s")
        },
        run=run,
    )
    out.mkdir(parents=True, exist_ok=True)
    for file in ("plan.json", "run-receipt.json"):
        write(out / file, (work / file).read_bytes())
    pack(out / POSITIONS, rows)
    pack(out / ATTEMPTS, [*original_rows, *extra])
    save_json(out / PAIR_FILE, pairs)
    save_json(out / "summary.json", summary)
    csv_file(out / "scores.csv", score)
    timing_chart(pairs, out / TIMING_PLOT)
    ancillary = []
    if amendment is not None:
        save_json(out / "affinity-amendment.json", amendment)
        save_json(out / "amended-pair.json", extra_pair)
        write(out / "amended-plan.json", (alternate / "plan.json").read_bytes())
        ancillary.extend(["affinity-amendment.json", "amended-pair.json", "amended-plan.json"])
    artifacts = (
        POSITIONS,
        ATTEMPTS,
        PAIR_FILE,
        "summary.json",
        "scores.csv",
        "plan.json",
        "run-receipt.json",
        TIMING_PLOT,
        *ancillary,
    )
    save_json(
        out / "roof-lock.json",
        dict(
            cases=cases,
            files={k: authority.sha(out / k) for k in artifacts},
            scoring_sha256=authority.sha(Path(__file__)),
        ),
    )
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=CHART,
                    method=trial.CANDIDATE,
                    scope="roof",
                    cases="sealed",
                    title="Fresh same-core aligned v5 and RF preflight",
                    caption=(
                        "Complete stored GLRT factors and matching causal requests. The workers "
                        "in each pair ran on the same core."
                    ),
                    seal="roof-lock.json",
                    provenance=[PAIR_FILE, "scores.csv", "summary.json"],
                    series=[
                        dict(
                            key="one",
                            label="Fresh guarded finish",
                            file=POSITIONS,
                            value=trial.CANDIDATE,
                        ),
                        dict(
                            key="stock",
                            label="Fresh aligned finish",
                            file=POSITIONS,
                            value=trial.STOCK,
                            match=list(MATCH),
                        ),
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--output", type=Path, default=trial.REPORT)
    parser.add_argument("--alternate", type=Path)
    args = parser.parse_args()
    publish(args.work, local_output(args.output), args.alternate)
