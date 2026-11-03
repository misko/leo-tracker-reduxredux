"""Viterbi peak-choice prototype for the group-recovered NORAD 62953/RX1 track."""

from __future__ import annotations

import argparse
import csv
import io
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from orbit_backfill_prototype import (
    OUTPUT_DIR,
    ROOT,
    SESSIONS,
    SOURCE_DIR,
    build_initial_inventory,
    file_digest,
    load_archived_session,
    serializable,
)
from plot_62953_diagnostic import (
    CATALOG_NUMBER,
    MAX_GAP_S,
    MINIMUM_SEED_GROUPS,
    POSTERIOR_MINIMUM,
    RECEIVER,
    RESIDUAL_MAXIMUM_HZ,
    RUNNER_UP_MAXIMUM,
    aggregate_groups,
    contiguous_group_segments,
)

SESSION = SESSIONS[1]
OUTPUT_STEM = "norad-62953-rx1-viterbi-prototype"
CONTINUITY_WEIGHT = 0.25
TRANSITION_SCALE_HZ = 100.0


def huber(values):
    values = np.abs(np.asarray(values, dtype=float))
    return np.where(values <= 1.0, 0.5 * values**2, values - 0.5)


def viterbi_peak_path(
    candidate_rows,
    posterior,
    residual_hz,
    column,
    group_support,
    *,
    continuity_weight=CONTINUITY_WEIGHT,
    transition_scale_hz=TRANSITION_SCALE_HZ,
):
    """Choose one target peak per group using conditional evidence and residual continuity."""
    posterior = np.asarray(posterior, dtype=float)
    residual_hz = np.asarray(residual_hz, dtype=float)
    group_support = np.asarray(group_support, dtype=float)
    states = [np.asarray(rows, dtype=int) for rows in candidate_rows]
    if (
        not states
        or len(states) != len(group_support)
        or any(rows.ndim != 1 or not len(rows) for rows in states)
        or posterior.ndim != 2
        or residual_hz.shape != (posterior.shape[0],)
        or not 0 <= column < posterior.shape[1]
        or np.any(group_support <= 0)
        or not np.isfinite(continuity_weight)
        or continuity_weight < 0
        or not np.isfinite(transition_scale_hz)
        or transition_scale_hz <= 0
    ):
        raise ValueError("invalid aligned Viterbi peak-path inputs")
    for index, rows in enumerate(states):
        if np.any(rows < 0) or np.any(rows >= len(posterior)):
            raise ValueError("candidate row is outside the posterior array")
        if np.any(posterior[rows, column] <= 0):
            raise ValueError("candidate target posterior must be positive")
        if np.sum(posterior[rows, column]) > group_support[index] + 1e-8:
            raise ValueError("candidate probability exceeds its group support")

    def emission(index):
        conditional = posterior[states[index], column] / group_support[index]
        return -np.log(np.maximum(conditional, np.finfo(float).tiny))

    costs = emission(0)
    backpointers = []
    for index in range(1, len(states)):
        previous = states[index - 1]
        current = states[index]
        transitions = continuity_weight * huber(
            (residual_hz[current, None] - residual_hz[previous][None, :])
            / transition_scale_hz
        )
        combined = transitions + costs[None, :]
        backpointer = np.argmin(combined, axis=1)
        costs = emission(index) + combined[np.arange(len(current)), backpointer]
        backpointers.append(backpointer)

    state_index = int(np.argmin(costs))
    path = [int(states[-1][state_index])]
    for index in range(len(states) - 2, -1, -1):
        state_index = int(backpointers[index][state_index])
        path.append(int(states[index][state_index]))
    return np.asarray(path[::-1], dtype=int)


def candidate_states(arrays, column, receiver, segment):
    groups = np.asarray(arrays["group"], dtype=int)
    receivers = np.asarray(arrays["receiver"], dtype=int)
    posterior = np.asarray(arrays["posterior"], dtype=float)
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]
    competitors = np.delete(posterior, column, axis=1)
    runner_up = np.max(competitors, axis=1) if competitors.shape[1] else np.zeros(len(groups))
    states = []
    for record in segment:
        rows = np.flatnonzero(
            (groups == record["group"])
            & (receivers == receiver)
            & (posterior[:, column] > 0)
            & (runner_up <= RUNNER_UP_MAXIMUM)
            & (np.abs(residual) <= RESIDUAL_MAXIMUM_HZ)
        )
        if not len(rows):
            raise ValueError(f"selected group {record['group']} has no eligible peak state")
        states.append(rows)
    return states


def path_metrics(path, states, posterior, residual_hz, column, group_support):
    path = np.asarray(path, dtype=int)
    residual = np.asarray(residual_hz, dtype=float)[path]
    conditional = np.asarray(
        [
            posterior[row, column] / support
            for row, support in zip(path, group_support, strict=True)
        ],
        dtype=float,
    )
    transition_terms = huber(np.diff(residual) / TRANSITION_SCALE_HZ)
    return {
        "group_count": len(path),
        "emission_negative_log_likelihood": float(np.sum(-np.log(conditional))),
        "unweighted_transition_huber_cost": float(np.sum(transition_terms)),
        "weighted_objective": float(
            np.sum(-np.log(conditional)) + CONTINUITY_WEIGHT * np.sum(transition_terms)
        ),
        "absolute_residual_median_hz": float(np.median(np.abs(residual))),
        "absolute_residual_p95_hz": float(np.quantile(np.abs(residual), 0.95)),
        "residual_rms_hz": float(np.sqrt(np.mean(residual**2))),
        "absolute_step_median_hz": float(np.median(np.abs(np.diff(residual)))),
        "absolute_step_p95_hz": float(np.quantile(np.abs(np.diff(residual)), 0.95)),
        "conditional_peak_share_median": float(np.median(conditional)),
        "conditional_peak_share_minimum": float(np.min(conditional)),
    }


def write_path_csv(path, segment, states, independent, viterbi, arrays, column):
    posterior = np.asarray(arrays["posterior"], dtype=float)
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]
    stream = io.StringIO()
    fields = [
        "group",
        "time_s",
        "channel",
        "seed",
        "group_support",
        "eligible_candidate_count",
        "independent_row",
        "independent_conditional_share",
        "independent_residual_hz",
        "viterbi_row",
        "viterbi_conditional_share",
        "viterbi_residual_hz",
        "choice_changed",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for record, candidates, local_row, path_row in zip(
        segment, states, independent, viterbi, strict=True
    ):
        support = record["target_support"]
        writer.writerow(
            {
                "group": record["group"],
                "time_s": record["time_s"],
                "channel": record["channel"],
                "seed": record["seed"],
                "group_support": support,
                "eligible_candidate_count": len(candidates),
                "independent_row": int(local_row),
                "independent_conditional_share": posterior[local_row, column] / support,
                "independent_residual_hz": residual[local_row],
                "viterbi_row": int(path_row),
                "viterbi_conditional_share": posterior[path_row, column] / support,
                "viterbi_residual_hz": residual[path_row],
                "choice_changed": bool(local_row != path_row),
            }
        )
    path.write_text(stream.getvalue())


def _plot(arrays, column, segment, states, independent, viterbi, output_paths):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    posterior = np.asarray(arrays["posterior"], dtype=float)
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]
    times = np.asarray([record["time_s"] for record in segment], dtype=float)
    support = np.asarray([record["target_support"] for record in segment], dtype=float)
    seed = np.asarray([record["seed"] for record in segment], dtype=bool)
    independent_residual = residual[independent]
    viterbi_residual = residual[viterbi]
    independent_share = posterior[independent, column] / support
    viterbi_share = posterior[viterbi, column] / support
    changed = independent != viterbi

    figure = plt.figure(figsize=(14, 11.5))
    grid = figure.add_gridspec(
        4,
        1,
        height_ratios=(2.4, 1.55, 1.35, 0.85),
        left=0.17,
        right=0.98,
        bottom=0.08,
        top=0.89,
        hspace=0.15,
    )
    residual_axis = figure.add_subplot(grid[0])
    probability_axis = figure.add_subplot(grid[1], sharex=residual_axis)
    step_axis = figure.add_subplot(grid[2], sharex=residual_axis)
    timeline = figure.add_subplot(grid[3], sharex=residual_axis)

    for time_value, rows in zip(times, states, strict=True):
        residual_axis.scatter(
            np.full(len(rows), time_value),
            residual[rows],
            s=16,
            color="0.72",
            alpha=0.55,
            linewidths=0,
        )
    residual_axis.plot(
        times,
        independent_residual,
        color="#E69F00",
        linewidth=0.8,
        alpha=0.75,
    )
    residual_axis.scatter(
        times,
        independent_residual,
        color="#E69F00",
        marker="x",
        s=28,
        linewidths=1.0,
        label="Independent target-MAP peak",
        zorder=4,
    )
    residual_axis.plot(times, viterbi_residual, color="#0072B2", linewidth=1.25)
    residual_axis.scatter(
        times,
        viterbi_residual,
        color="#0072B2",
        s=20,
        linewidths=0,
        label="Viterbi peak path",
        zorder=5,
    )
    residual_axis.scatter(
        times[changed],
        viterbi_residual[changed],
        facecolors="none",
        edgecolors="#CC3311",
        s=65,
        linewidths=1.1,
        label="Choice changed",
        zorder=6,
    )
    residual_axis.axhline(0, color="black", linewidth=0.7)
    residual_axis.axhline(150, color="#CC79A7", linestyle="--", linewidth=0.8)
    residual_axis.axhline(-150, color="#CC79A7", linestyle="--", linewidth=0.8)
    residual_axis.set_ylim(-175, 175)
    residual_axis.set_ylabel("Selected residual (Hz)")
    residual_axis.legend(loc="upper right", ncol=3, fontsize=8)

    probability_axis.plot(times, support, color="0.45", linewidth=1.0)
    probability_axis.scatter(
        times, support, color="0.45", s=12, label="Group support for 62953"
    )
    probability_axis.scatter(
        times,
        independent_share,
        color="#E69F00",
        marker="x",
        s=25,
        label="Independent conditional share",
    )
    probability_axis.scatter(
        times,
        viterbi_share,
        color="#0072B2",
        s=18,
        label="Viterbi conditional share",
    )
    probability_axis.set_ylim(0, 1.03)
    probability_axis.set_ylabel("Probability / share")
    probability_axis.legend(loc="lower right", ncol=3, fontsize=8)

    step_times = times[1:]
    step_axis.plot(
        step_times,
        np.abs(np.diff(independent_residual)),
        color="#E69F00",
        linewidth=1.0,
        label="Independent |residual step|",
    )
    step_axis.plot(
        step_times,
        np.abs(np.diff(viterbi_residual)),
        color="#0072B2",
        linewidth=1.2,
        label="Viterbi |residual step|",
    )
    step_axis.set_ylabel("Step magnitude (Hz)")
    step_axis.set_ylim(bottom=0)
    step_axis.legend(loc="upper right", ncol=2, fontsize=8)

    timeline.plot([times[0], times[-1]], [0, 0], color="#009E73", linewidth=2)
    timeline.scatter(times[~seed], np.zeros(np.sum(~seed)), color="#E69F00", s=24)
    timeline.scatter(times[seed], np.zeros(np.sum(seed)), color="#0072B2", s=24)
    timeline.scatter(times[changed], np.ones(np.sum(changed)), color="#CC3311", marker="|", s=80)
    timeline.set_yticks(
        [0, 1],
        labels=[
            "153 retained groups\n93 seed / 60 new",
            f"{int(np.sum(changed))} choices changed",
        ],
    )
    timeline.set_ylim(-0.45, 1.45)
    timeline.set_xlabel("Receive time since capture start (s)")

    for axis in (residual_axis, probability_axis, step_axis, timeline):
        axis.set_xlim(times[0] - 1, times[-1] + 1)
        axis.grid(alpha=0.18)
    for axis in (residual_axis, probability_axis, step_axis):
        axis.tick_params(labelbottom=False)

    figure.suptitle(
        "Scan B · NORAD 62953 / RX1 · conditional peak Viterbi prototype\n"
        "Group memberships fixed; light residual continuity resolves within-group peak ambiguity",
        y=0.98,
    )
    figure.legend(
        handles=[
            Line2D([], [], marker="o", color="0.72", linestyle="", label="Eligible peak state"),
            Line2D([], [], marker="o", color="#0072B2", linestyle="", label="Seed group"),
            Line2D([], [], marker="o", color="#E69F00", linestyle="", label="Unallocated fill"),
            Line2D([], [], marker="|", color="#CC3311", linestyle="", label="Viterbi differs from MAP"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.925),
        ncol=4,
        fontsize=8,
    )
    figure.text(
        0.5,
        0.018,
        "Emission = −log(candidate posterior / 62953 group support). Transition = 0.25 × "
        "Huber(Δresidual / 100 Hz). Membership remains the group-summed ≥0.90 diagnostic; "
        "this peak path is a sensitivity prototype, not validated truth.",
        ha="center",
        fontsize=8,
    )
    for path in output_paths:
        figure.savefig(path, dpi=180)
    plt.close(figure)


def render(output_dir=OUTPUT_DIR, source_dir=SOURCE_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_paths = [output_dir / f"{OUTPUT_STEM}{suffix}" for suffix in (".png", ".svg")]
    csv_path = output_dir / f"{OUTPUT_STEM}.csv"
    receipt_path = output_dir / f"{OUTPUT_STEM}.json"
    existing = [path for path in (*image_paths, csv_path, receipt_path) if path.exists()]
    if existing:
        raise FileExistsError(", ".join(map(str, existing)))

    arrays, metadata, array_path, source_receipt = load_archived_session(SESSION, source_dir)
    column = list(map(int, arrays["catalog_numbers"])).index(CATALOG_NUMBER)
    scan_dir = ROOT / "scans" / SESSION
    bundle_path = scan_dir / "bundle.npz"
    seed_path = scan_dir / "seed.json"
    bundle = np.load(bundle_path)
    seed = json.loads(seed_path.read_text())
    owners, proposals = build_initial_inventory(
        seed,
        bundle["group"],
        bundle["times"],
        bundle["channel"],
        arrays["catalog_numbers"],
    )
    initial = proposals[(CATALOG_NUMBER, RECEIVER)]
    seed_groups = set().union(*(proposal["groups"] for proposal in initial))
    records = aggregate_groups(
        arrays, column, RECEIVER, seed_groups, owners, CATALOG_NUMBER
    )
    segments = [
        segment
        for segment in contiguous_group_segments(records)
        if sum(record["seed"] for record in segment) >= MINIMUM_SEED_GROUPS
    ]
    segment = max(
        segments,
        key=lambda values: (
            values[-1]["time_s"] - values[0]["time_s"],
            len(values),
        ),
    )
    states = candidate_states(arrays, column, RECEIVER, segment)
    posterior = np.asarray(arrays["posterior"], dtype=float)
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]
    support = np.asarray([record["target_support"] for record in segment], dtype=float)
    independent = np.asarray(
        [int(rows[np.argmax(posterior[rows, column])]) for rows in states], dtype=int
    )
    viterbi = viterbi_peak_path(states, posterior, residual, column, support)
    independent_metrics = path_metrics(
        independent, states, posterior, residual, column, support
    )
    viterbi_metrics = path_metrics(viterbi, states, posterior, residual, column, support)
    changed = int(np.sum(independent != viterbi))
    transition_reduction = 1.0 - (
        viterbi_metrics["unweighted_transition_huber_cost"]
        / independent_metrics["unweighted_transition_huber_cost"]
    )
    emission_increase = (
        viterbi_metrics["emission_negative_log_likelihood"]
        / independent_metrics["emission_negative_log_likelihood"]
        - 1.0
    )

    write_path_csv(csv_path, segment, states, independent, viterbi, arrays, column)
    _plot(arrays, column, segment, states, independent, viterbi, image_paths)
    result = {
        "schema": "ds13-norad-62953-viterbi-prototype/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "session": SESSION,
        "scan_label": "B",
        "catalog_number": CATALOG_NUMBER,
        "receiver": RECEIVER,
        "source_profile": metadata["source_profile"],
        "membership": {
            "semantics": "Fixed group-summed diagnostic membership; Viterbi changes only peak choice.",
            "start_s": segment[0]["time_s"],
            "end_s": segment[-1]["time_s"],
            "duration_s": segment[-1]["time_s"] - segment[0]["time_s"],
            "group_count": len(segment),
            "seed_group_count": sum(record["seed"] for record in segment),
            "unallocated_group_count": sum(not record["seed"] for record in segment),
            "group_support_minimum": POSTERIOR_MINIMUM,
            "maximum_gap_s": MAX_GAP_S,
        },
        "viterbi": {
            "emission": "-log(row target posterior / target group support)",
            "transition": "continuity_weight * Huber(delta residual / transition_scale_hz)",
            "continuity_weight": CONTINUITY_WEIGHT,
            "transition_scale_hz": TRANSITION_SCALE_HZ,
            "eligible_peak_residual_maximum_hz": RESIDUAL_MAXIMUM_HZ,
            "eligible_peak_runner_up_maximum": RUNNER_UP_MAXIMUM,
            "candidate_state_count": sum(len(rows) for rows in states),
            "candidate_states_per_group": dict(sorted(Counter(map(len, states)).items())),
            "choice_changed_count": changed,
            "choice_changed_fraction": changed / len(segment),
            "transition_cost_reduction_fraction": transition_reduction,
            "emission_nll_increase_fraction": emission_increase,
            "independent_map": independent_metrics,
            "viterbi_path": viterbi_metrics,
            "qualification": (
                "Sensitivity prototype only. No labeled peak identity validates the transition "
                "weight; report the independent and smoothed paths together."
            ),
        },
        "source_hashes": {
            str(array_path.resolve()): file_digest(array_path),
            str(source_receipt.resolve()): file_digest(source_receipt),
            str(bundle_path.resolve()): file_digest(bundle_path),
            str(seed_path.resolve()): file_digest(seed_path),
            str(Path(__file__).resolve()): file_digest(__file__),
        },
        "outputs": {
            str(path.resolve()): file_digest(path) for path in (*image_paths, csv_path)
        },
    }
    receipt_path.write_text(json.dumps(serializable(result), indent=2, allow_nan=False) + "\n")
    arrays.close()
    bundle.close()
    return result, image_paths, csv_path, receipt_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    args = parser.parse_args(argv)
    result, images, csv_path, receipt = render(args.output_dir, args.source_dir)
    print(
        json.dumps(
            serializable(
                {
                    "membership": result["membership"],
                    "viterbi": result["viterbi"],
                    "images": images,
                    "path_csv": csv_path,
                    "receipt": receipt,
                }
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
