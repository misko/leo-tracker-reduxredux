"""Authenticate the blind regional null trial, score decisions and draw the evidence."""

import argparse
import json
from collections import Counter
from pathlib import Path

from ..__main__ import read_predictions, save_json, write
from ..scoring import ARMS, distance_km, distribution, thresholds
from . import native_joint_full_results as shared
from . import region_null_trial as trial
from . import screening_figures
from .outside_predictive_results import CONDITIONS

phase = trial.phase
METHOD, SMOOTH = trial.METHOD, trial.base.clock.METHOD
PREDICTIONS = f"{METHOD}.jsonl.gz"
COHORTS = ("fresh-synthetic", "archived-roof", "shuffled-native")
QUANTITIES = (
    "original_rms_hz",
    "original_held_rf_hz",
    "original_held_orbits",
    "retained_rms_hz",
    "retained_held_rf_hz",
    "wall_s",
    "cpu_s",
    "gate_wall_s",
    "gate_cpu_s",
    "peak_rss_kib",
    "peak_address_space_kib",
    "null_rank",
    "inside_minus_exterior",
    "signal_above_null",
    "inside_orbits",
    "exterior_orbits",
    "arcs",
    "padded_orbits",
)


def verify(records, queries):
    old = trial.base.exterior.prior_cases()[1]
    observations = {}
    for ident, row in records.items():
        expected = trial.base.clock.bindings(queries[ident]) | {"method": METHOD}
        if any(row[k] != value for k, value in expected.items()):
            raise ValueError(f"{ident} native or tile binding mismatch")
        if row["result"]["status"] not in ("ok", "withheld"):
            continue
        graph = row["observation_sha256"]
        if observations.setdefault(row["recording"], graph) != graph:
            raise ValueError("identical native queries changed their Graph under a different offer")
        if row["cohort"] == "archived-roof":
            prior = old[ident]
            if graph != prior["observation_sha256"] or any(
                row["initial"].get(k) != prior["result"].get(k)
                for k in ("status", "arms", "reason")
            ):
                raise ValueError("fresh smooth first pass differs from its sealed counterpart")


def score_rows(records, labels):
    out = []
    for ident, row in records.items():
        label, gate = labels[ident], row.get("gate", {})
        initial, result = row.get("initial", row["result"]), row["result"]
        held = initial.get("metrics", {}).get("held_by_arm", {})
        inside, exterior = gate.get("inside", {}), gate.get("exterior", {})
        for arm in ARMS:
            first, last = initial["arms"][arm], result["arms"][arm]
            held_arm = held.get(arm, {})
            out.append(
                dict(
                    id=ident,
                    arm=arm,
                    cohort=row["cohort"],
                    recording=row["recording"],
                    source=label["source_label"],
                    condition=label["condition"],
                    truth_margin_km=label["margin_km"],
                    original_status=initial["status"],
                    original_reason=initial.get("reason"),
                    status=result["status"],
                    reason=result.get("reason"),
                    state=gate.get("state", result["status"]),
                    original_error_km=distance_km(first.get("latlon"), label["truth"]),
                    retained_error_km=distance_km(last.get("latlon"), label["truth"]),
                    original_forced_error_km=distance_km(
                        first.get("forced_latlon"), label["truth"]
                    ),
                    original_rms_hz=first.get("rf_rms_hz"),
                    retained_rms_hz=last.get("rf_rms_hz") if last.get("latlon") else None,
                    original_held_rf_hz=held_arm.get("held_rf_rms_hz"),
                    original_held_orbits=held_arm.get("held_orbits"),
                    retained_held_rf_hz=held_arm.get("held_rf_rms_hz")
                    if last.get("latlon")
                    else None,
                    clock_hz_per_ghz=first.get("c_hz_per_ghz"),
                    null_rank=gate.get("null_rank"),
                    inside_score=inside.get("score"),
                    exterior_score=exterior.get("score"),
                    inside_orbits=inside.get("orbits"),
                    exterior_orbits=exterior.get("orbits"),
                    max_null=gate.get("max_null"),
                    inside_minus_exterior=gate.get("inside_minus_exterior"),
                    signal_above_null=(
                        max(inside["score"], exterior["score"]) - gate["max_null"]
                        if inside
                        else None
                    ),
                    arcs=gate.get("arcs"),
                    padded_orbits=gate.get("padded_orbits"),
                    permutations=gate.get("permutations"),
                    wall_s=row.get("worker_wall_s"),
                    cpu_s=row.get("worker", {}).get("cpu_s"),
                    gate_wall_s=row.get("gate_time", {}).get("wall_s"),
                    gate_cpu_s=row.get("gate_time", {}).get("cpu_s"),
                    peak_rss_kib=row.get("resident_peak_kib"),
                    peak_address_space_kib=row.get("proc_memory_kib", {}).get("VmPeak"),
                )
            )
    return out


def aggregate(rows):
    groups = []
    for cohort in COHORTS:
        for arm in ARMS:
            matched = [r for r in rows if r["cohort"] == cohort and r["arm"] == arm]
            signed = [r for r in matched if r["truth_margin_km"] is not None]
            for group, selected in (
                ("all", matched),
                ("containing", [r for r in signed if r["truth_margin_km"] > 0]),
                ("omitted", [r for r in signed if r["truth_margin_km"] < 0]),
                *((c, [r for r in matched if r["condition"] == c]) for c in CONDITIONS),
            ):
                if not selected:
                    continue
                groups.append(
                    dict(
                        cohort=cohort,
                        arm=arm,
                        condition=group,
                        scheduled=len(selected),
                        captures=len({r["recording"] for r in selected}),
                        before=dict(Counter(r["original_status"] for r in selected)),
                        after=dict(Counter(r["status"] for r in selected)),
                        gates=dict(Counter(r["state"] for r in selected)),
                        reasons=dict(Counter(r["reason"] for r in selected if r["reason"])),
                        before_error_km=distribution(r["original_error_km"] for r in selected),
                        after_error_km=distribution(r["retained_error_km"] for r in selected),
                        within_km=thresholds([r["retained_error_km"] for r in selected]),
                        **{k: distribution(r[k] for r in selected) for k in QUANTITIES},
                    )
                )
    return groups


def manifests(output, records, labels, lock):
    for cohort, title in zip(
        COHORTS[:2],
        (
            "Track-time null at two new synthetic sites",
            "Track-time null on two measured roof recordings",
        ),
        strict=True,
    ):
        group = [r for r in records.values() if r["cohort"] == cohort]
        cases = [r["id"] for r in group]
        folder = output / cohort
        queries = [
            dict(
                id=r["id"],
                condition=labels[r["id"]]["condition"],
                recording=labels[r["id"]]["source_label"],
                truth=labels[r["id"]]["truth"],
                bindings={k: r[k] for k in ("input_sha256", "native_sha256", "catalog_sha256")},
            )
            for r in group
        ]
        candidate = [
            dict(
                r,
                result=dict(
                    r["result"],
                    arms={a: dict(v, forced_latlon=None) for a, v in r["result"]["arms"].items()},
                ),
            )
            for r in group
        ]
        stock = [dict(r, method=SMOOTH, result=r.get("initial", r["result"])) for r in group]
        save_json(folder / "figure-queries.json", dict(queries=queries))
        files = {"figure-queries.json": phase.digest(folder / "figure-queries.json")}
        for method, rows in ((METHOD, candidate), (SMOOTH, stock)):
            name = f"{method}.jsonl.gz"
            files[name] = shared.pack(folder, name, rows)
        save_json(
            folder / "figure-lock.json",
            dict(cases=cases, files=files, main_prediction_sha256=lock["files"][PREDICTIONS]),
        )
        seen = {r["condition"] for r in queries}
        spec = dict(
            id=f"{METHOD}-{cohort}",
            method=METHOD,
            scope="transfer",
            title=title,
            caption="Same native factors, anonymous Graph and causal catalogue for both series.",
            cases=cases,
            seal="figure-lock.json",
            queries="figure-queries.json",
            condition_labels={k: v for k, v in CONDITIONS.items() if k in seen},
            series=[
                dict(key="candidate", label="Track-time null gate", file=PREDICTIONS, value=METHOD),
                dict(
                    key="stock",
                    label="Native smooth",
                    forced_label="Smooth · forced",
                    file=f"{SMOOTH}.jsonl.gz",
                    value=SMOOTH,
                    match=["input_sha256", "tile"],
                ),
            ],
        )
        write(
            folder / "figures.json",
            json.dumps(dict(version=1, charts=[spec]), indent=2).encode() + b"\n",
        )


def plot_evidence(output, rows):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axs = plt.subplots(1, 2, figsize=(11.6, 4.9), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.085, right=0.977, bottom=0.19, top=0.82, wspace=0.10)
    for ax, cohort, title in zip(
        axs, COHORTS[:2], ("Two synthetic sites", "Two archived roof recordings"), strict=True
    ):
        all_rows = [r for r in rows if r["arm"] == "c0" and r["cohort"] == cohort]
        evaluated = [r for r in all_rows if r["signal_above_null"] is not None]
        first_capture = sorted({r["recording"] for r in all_rows})[0]
        ax.axvline(-1, c="#7e8790", linestyle="--", lw=1)
        ax.axvline(1, c="#7e8790", linestyle="--", lw=1)
        ax.axhline(0, c="#7e8790", linestyle="--", lw=1)
        for r in evaluated:
            omitted = r["truth_margin_km"] < 0
            ax.scatter(
                r["inside_minus_exterior"],
                r["signal_above_null"],
                s=82,
                marker="o" if r["recording"] == first_capture else "s",
                color="#ba5a24" if omitted else "#17748e",
                alpha=0.85,
                edgecolor="#252729" if r["original_status"] == "ok" else "white",
            )
        clustered = [r for r in evaluated if r["signal_above_null"] < 0]
        if clustered and cohort == "archived-roof":
            ax.annotate(
                f"{len(clustered)} offers below the null cutoff",
                (clustered[0]["inside_minus_exterior"], clustered[0]["signal_above_null"]),
                xytext=(22, 18),
                textcoords="offset points",
                fontsize=8,
                color="#414751",
                arrowprops=dict(arrowstyle="-", color="#6f7680", lw=0.8),
            )
        ax.set_title(f"{title} · {len(evaluated)}/{len(all_rows)} scored", fontsize=12, loc="left")
        ax.set_xlabel("Inside − exterior score (orbit-equivalents)")
        ax.grid(alpha=0.15)
    axs[0].set_ylabel("Best observed − strongest permutation\n(orbit-equivalents)")
    axs[1].legend(
        handles=[
            Line2D([], [], color="#17748e", marker="o", linestyle="None", label="Containing offer"),
            Line2D([], [], color="#ba5a24", marker="o", linestyle="None", label="Omitted site"),
            Line2D(
                [],
                [],
                color="#2a2d2f",
                marker="o",
                markerfacecolor="white",
                linestyle="None",
                label="Original receiver published (dark rim)",
            ),
        ],
        loc="upper right",
        fontsize=8,
    )
    fig.suptitle("Causal satellite evidence and tile discrimination", fontsize=15, y=0.975)
    fig.text(
        0.05,
        0.025,
        "Shapes identify captures. Dashes mark the frozen score cutoffs. "
        "An inside win also requires four nominated orbits.",
        fontsize=9,
    )
    fig.savefig(output / "null-evidence.png", dpi=180)
    fig.savefig(output / "null-evidence.pdf")
    plt.close(fig)


def score(output, work):
    lock = phase._read(output / "prediction-lock.json")
    trial.base.clock.base.secant_full._verify_files(output, lock["files"])
    plan = phase._read(output / "roster.json")
    oracle = work / "evaluator.json"
    if not oracle.exists():
        oracle = output / "evaluator.json"
    if phase.digest(oracle) != plan["evaluator_sha256"]:
        raise ValueError("blinded evaluator labels changed")
    records = read_predictions(output / PREDICTIONS)
    labels = phase._read(oracle)["labels"]
    queries = {q["id"]: q for q in plan["cases"]}
    if not set(records) == set(labels) == set(queries) == set(lock["cases"]):
        raise ValueError("incomplete query lineage")
    verify(records, queries)
    repair_path = output / "shuffled-control-lock.json"
    repaired = []
    if repair_path.exists():
        repair = phase._read(repair_path)
        trial.base.clock.base.secant_full._verify_files(output, repair["files"])
        requests = phase._read(output / "shuffled-control-requests.json")
        if requests["original_prediction_sha256"] != phase.digest(output / "prediction-lock.json"):
            raise ValueError("serialization repair refers to another trial")
        expected = {q["id"]: q for q in requests["cases"]}
        corrected = read_predictions(output / "shuffled-controls.jsonl.gz")
        negatives = {qid for qid, q in queries.items() if q["cohort"] == "shuffled-native"}
        if not set(corrected) == set(expected) == set(repair["cases"]) == negatives:
            raise ValueError("the serialization repair did not cover the original two controls")
        for ident, fixed in expected.items():
            deltas = {
                k for k in fixed["packet"] if fixed["packet"][k] != queries[ident]["packet"][k]
            }
            if deltas != {"native"} or records[ident]["result"]["status"] != "failed":
                raise ValueError("a non-serialization input was changed")
        verify(corrected, expected)
        repaired = sorted(corrected)
        records.update(corrected)
    write(output / "evaluator.json", oracle.read_bytes())
    rows = score_rows(records, labels)
    shared.csv_file(output / "scores.csv", rows)
    save_json(
        output / "summary.json",
        dict(
            groups=aggregate(rows),
            elapsed_s=lock["elapsed_s"],
            repaired_serialization_controls=repaired,
        ),
    )
    manifests(output, records, labels, lock)
    plot_evidence(output, rows)
    screening_figures.generate(output / "charts", evidence=output)
    files = [
        path for path in output.rglob("*") if path.is_file() and path.name != "result-lock.json"
    ]
    save_json(
        output / "result-lock.json",
        dict(
            scorer_sha256=phase.digest(Path(__file__)),
            files={str(path.relative_to(output)): phase.digest(path) for path in files},
        ),
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, default=trial.REPORT)
    cli.add_argument("--work", type=Path, default=trial.WORK)
    args = cli.parse_args()
    score(args.output, args.work)


if __name__ == "__main__":
    main()
