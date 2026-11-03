"""Explain why the row-gated orbit backfill rejected Scan B NORAD 62953/RX1."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from orbit_backfill_prototype import (
    MAX_GAP_S,
    MINIMUM_SEED_GROUPS,
    OUTPUT_DIR,
    POSTERIOR_MINIMUM,
    RESIDUAL_MAXIMUM_HZ,
    RETRIEVAL_GATE_HZ,
    ROOT,
    RUNNER_UP_MAXIMUM,
    SESSIONS,
    SOURCE_DIR,
    build_initial_inventory,
    file_digest,
    load_archived_session,
    serializable,
)

CATALOG_NUMBER = 62953
RECEIVER = 1
SESSION = SESSIONS[1]
OUTPUT_STEM = "norad-62953-rx1-association-diagnostic"


def aggregate_groups(arrays, column, receiver, seed_groups, owners, catalog_number):
    """Collapse row posteriors to the finite-set GLRT-group satellite marginal."""
    times = np.asarray(arrays["times_s"], dtype=float)
    groups = np.asarray(arrays["group"], dtype=int)
    receivers = np.asarray(arrays["receiver"], dtype=int)
    channels = np.asarray(arrays["channel"], dtype=int)
    posterior = np.asarray(arrays["posterior"], dtype=float)
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]
    if posterior.ndim != 2 or posterior.shape[0] != len(times):
        raise ValueError("posterior must be an aligned row/satellite matrix")
    if not 0 <= column < posterior.shape[1]:
        raise ValueError("satellite column is outside the posterior matrix")

    records = []
    same_receiver = receivers == receiver
    for group in np.unique(groups[same_receiver]):
        rows = np.flatnonzero(same_receiver & (groups == group))
        if len(np.unique(times[rows])) != 1 or len(np.unique(channels[rows])) != 1:
            raise ValueError("GLRT-group time, receiver, and channel must be constant")
        target = posterior[rows, column]
        target_support = float(np.sum(target))
        if target_support > 1.0 + 1e-8:
            raise ValueError("group target support exceeds a probability of one")
        best_row = int(rows[np.argmax(target)])
        competitors = np.delete(posterior[best_row], column)
        runner_up = float(np.max(competitors)) if len(competitors) else 0.0
        owner_set = owners.get(int(group), set())
        allowed = not owner_set or owner_set == {catalog_number}
        maximum_row = float(posterior[best_row, column])
        group_gate = (
            allowed
            and target_support >= POSTERIOR_MINIMUM
            and runner_up <= RUNNER_UP_MAXIMUM
            and abs(float(residual[best_row])) <= RESIDUAL_MAXIMUM_HZ
        )
        row_gate = allowed and bool(
            np.any(
                (target >= POSTERIOR_MINIMUM)
                & (
                    np.max(np.delete(posterior[rows], column, axis=1), axis=1)
                    <= RUNNER_UP_MAXIMUM
                    if posterior.shape[1] > 1
                    else np.ones(len(rows), dtype=bool)
                )
                & (np.abs(residual[rows]) <= RESIDUAL_MAXIMUM_HZ)
            )
        )
        group_satellite_support = np.sum(posterior[rows], axis=0)
        records.append(
            {
                "group": int(group),
                "time_s": float(times[best_row]),
                "channel": int(channels[best_row]),
                "seed": int(group) in seed_groups,
                "allowed": allowed,
                "owners": sorted(owner_set),
                "candidate_row_count": len(rows),
                "best_row": best_row,
                "target_support": target_support,
                "maximum_row_posterior": maximum_row,
                "conditional_best_row_share": (
                    maximum_row / target_support if target_support else 0.0
                ),
                "runner_up_at_best_row": runner_up,
                "best_residual_hz": float(residual[best_row]),
                "row_gate": row_gate,
                "group_gate": group_gate,
                "largest_group_marginal_column": int(np.argmax(group_satellite_support)),
            }
        )
    return records


def contiguous_group_segments(records, *, maximum_gap_s=MAX_GAP_S):
    selected = sorted(
        (record for record in records if record["group_gate"]),
        key=lambda record: (record["time_s"], record["group"]),
    )
    if not selected:
        return []
    cuts = [0]
    cuts.extend(
        index
        for index in range(1, len(selected))
        if selected[index]["time_s"] - selected[index - 1]["time_s"] > maximum_gap_s
    )
    cuts.append(len(selected))
    return [selected[start:end] for start, end in zip(cuts, cuts[1:])]


def _segment_summary(segment):
    return {
        "start_s": segment[0]["time_s"],
        "end_s": segment[-1]["time_s"],
        "duration_s": segment[-1]["time_s"] - segment[0]["time_s"],
        "group_count": len(segment),
        "seed_group_count": sum(record["seed"] for record in segment),
        "unallocated_group_count": sum(not record["seed"] for record in segment),
        "groups_by_channel": dict(
            sorted(Counter(record["channel"] for record in segment).items())
        ),
    }


def _row_tight_mask(arrays, column, receiver, owners, catalog_number):
    groups = np.asarray(arrays["group"], dtype=int)
    receivers = np.asarray(arrays["receiver"], dtype=int)
    posterior = np.asarray(arrays["posterior"], dtype=float)
    residual = np.abs(np.asarray(arrays["residual_hz"], dtype=float)[:, column])
    competitors = np.delete(posterior, column, axis=1)
    runner_up = np.max(competitors, axis=1) if competitors.shape[1] else np.zeros(len(groups))
    allowed = np.fromiter(
        (
            not owners.get(int(group), set())
            or owners.get(int(group), set()) == {catalog_number}
            for group in groups
        ),
        dtype=bool,
        count=len(groups),
    )
    return (
        (receivers == receiver)
        & allowed
        & (residual <= RETRIEVAL_GATE_HZ)
        & (posterior[:, column] >= POSTERIOR_MINIMUM)
        & (runner_up <= RUNNER_UP_MAXIMUM)
        & (residual <= RESIDUAL_MAXIMUM_HZ)
    )


def _row_segments(arrays, mask, seed_groups):
    times = np.asarray(arrays["times_s"], dtype=float)
    groups = np.asarray(arrays["group"], dtype=int)
    rows = np.flatnonzero(mask)
    rows = rows[np.argsort(times[rows], kind="stable")]
    cuts = np.flatnonzero(np.diff(times[rows]) > MAX_GAP_S) + 1
    return [
        {
            "start_s": float(times[segment[0]]),
            "end_s": float(times[segment[-1]]),
            "duration_s": float(times[segment[-1]] - times[segment[0]]),
            "row_count": len(segment),
            "seed_group_count": sum(int(groups[row]) in seed_groups for row in segment),
        }
        for segment in np.split(rows, cuts)
        if len(segment)
    ]


def _plot(arrays, column, initial, records, row_tight, selected, output_paths):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    times = np.asarray(arrays["times_s"], dtype=float)
    groups = np.asarray(arrays["group"], dtype=int)
    receiver = np.asarray(arrays["receiver"], dtype=int)
    doppler = np.asarray(arrays["doppler_hz"], dtype=float)[:, column]
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]
    seed_groups = set().union(*(proposal["groups"] for proposal in initial))
    start = min(proposal["start_s"] for proposal in initial) - 8.0
    end = max(selected[-1]["time_s"], max(p["end_s"] for p in initial)) + 7.0
    window = (times >= start) & (times <= end)
    near = window & (receiver == RECEIVER) & (np.abs(residual) <= RETRIEVAL_GATE_HZ)
    seed_rows = window & (receiver == RECEIVER) & np.isin(groups, list(seed_groups))
    seed_records = [record for record in records if record["seed"]]
    passing_seed = [record for record in seed_records if record["group_gate"]]
    failing_seed = [record for record in seed_records if not record["group_gate"]]

    figure = plt.figure(figsize=(14, 13))
    grid = figure.add_gridspec(
        4,
        1,
        height_ratios=(2.5, 1.45, 1.55, 1.15),
        left=0.15,
        right=0.98,
        bottom=0.075,
        top=0.91,
        hspace=0.16,
    )
    main = figure.add_subplot(grid[0])
    residual_axis = figure.add_subplot(grid[1], sharex=main)
    posterior_axis = figure.add_subplot(grid[2], sharex=main)
    timeline = figure.add_subplot(grid[3], sharex=main)

    dense_times = np.asarray(arrays["dense_times_s"], dtype=float)
    dense_window = (dense_times >= start) & (dense_times <= end)
    curve = np.asarray(arrays["dense_doppler_hz"], dtype=float)[dense_window, column]
    main.plot(dense_times[dense_window], curve / 1000, color="black", linewidth=1.5)
    main.scatter(
        times[near],
        doppler[near] / 1000,
        s=8,
        color="0.72",
        alpha=0.32,
        linewidths=0,
        rasterized=True,
    )
    main.scatter(
        times[seed_rows],
        doppler[seed_rows] / 1000,
        s=22,
        facecolors="none",
        edgecolors="#7B61A8",
        alpha=0.38,
        linewidths=0.8,
    )
    for records_subset, color, marker in (
        (passing_seed, "#009E73", "o"),
        (failing_seed, "#CC3311", "x"),
    ):
        indices = np.asarray([record["best_row"] for record in records_subset], dtype=int)
        main.scatter(
            times[indices],
            doppler[indices] / 1000,
            s=30,
            color=color,
            marker=marker,
            linewidths=1.0,
            zorder=5,
        )
    main.set_ylabel("Doppler (kHz)")
    main.set_ylim((float(np.min(curve)) - 3000) / 1000, (float(np.max(curve)) + 3000) / 1000)

    residual_axis.scatter(
        times[near], residual[near], s=7, color="0.72", alpha=0.28, linewidths=0
    )
    for records_subset, color, marker in (
        (passing_seed, "#009E73", "o"),
        (failing_seed, "#CC3311", "x"),
    ):
        indices = np.asarray([record["best_row"] for record in records_subset], dtype=int)
        residual_axis.scatter(
            times[indices],
            residual[indices],
            s=28,
            color=color,
            marker=marker,
            linewidths=1.0,
            zorder=5,
        )
    residual_axis.axhline(0, color="black", linewidth=0.7)
    residual_axis.axhline(150, color="#CC79A7", linestyle="--", linewidth=0.9)
    residual_axis.axhline(-150, color="#CC79A7", linestyle="--", linewidth=0.9)
    residual_axis.set_ylim(-500, 500)
    residual_axis.set_ylabel("GLRT − orbit (Hz)")

    ordered_seed = sorted(seed_records, key=lambda record: record["time_s"])
    seed_times = np.asarray([record["time_s"] for record in ordered_seed])
    group_support = np.asarray([record["target_support"] for record in ordered_seed])
    row_support = np.asarray([record["maximum_row_posterior"] for record in ordered_seed])
    posterior_axis.vlines(seed_times, row_support, group_support, color="0.78", linewidth=0.7)
    posterior_axis.scatter(
        seed_times,
        group_support,
        s=24,
        color="#0072B2",
        label="62953 support summed within GLRT group",
        zorder=4,
    )
    posterior_axis.scatter(
        seed_times,
        row_support,
        s=22,
        color="#E69F00",
        marker="x",
        label="Largest individual-row posterior",
        zorder=5,
    )
    posterior_axis.axhline(POSTERIOR_MINIMUM, color="black", linestyle="--", linewidth=0.9)
    posterior_axis.set_ylim(0, 1.03)
    posterior_axis.set_ylabel("Association probability")
    posterior_axis.legend(loc="lower left", ncol=2, fontsize=8)

    row_times = times[row_tight]
    row_seed = np.isin(groups[row_tight], list(seed_groups))
    timeline.scatter(row_times[~row_seed], np.zeros(np.sum(~row_seed)), color="#E69F00", s=24)
    timeline.scatter(row_times[row_seed], np.zeros(np.sum(row_seed)), color="#0072B2", s=24)
    selected_times = np.asarray([record["time_s"] for record in selected])
    selected_seed = np.asarray([record["seed"] for record in selected])
    timeline.plot(
        [selected_times[0], selected_times[-1]], [1, 1], color="#009E73", linewidth=2
    )
    timeline.scatter(
        selected_times[~selected_seed],
        np.ones(np.sum(~selected_seed)),
        color="#E69F00",
        s=19,
        zorder=4,
    )
    timeline.scatter(
        selected_times[selected_seed],
        np.ones(np.sum(selected_seed)),
        color="#0072B2",
        s=19,
        zorder=4,
    )
    for y, channel in ((2, 3), (3, 4)):
        proposal = next(value for value in initial if value["channels"] == [channel])
        timeline.plot(
            [proposal["start_s"], proposal["end_s"]],
            [y, y],
            color="0.62",
            linewidth=5,
            solid_capstyle="round",
        )
        channel_records = [record for record in seed_records if record["channel"] == channel]
        timeline.scatter(
            [record["time_s"] for record in channel_records],
            np.full(len(channel_records), y),
            color="0.35",
            s=11,
            zorder=4,
        )
    timeline.set_yticks(
        [0, 1, 2, 3],
        labels=[
            "Current row gate\n24 rows / 8 seeds",
            "Group-summed diagnostic\n153 groups / 93 seeds",
            "Initial CH3\n67 seeds",
            "Initial CH4\n47 seeds",
        ],
    )
    timeline.set_ylim(-0.55, 3.55)
    timeline.set_xlabel("Receive time since capture start (s)")

    for axis in (main, residual_axis, posterior_axis, timeline):
        axis.set_xlim(start, end)
        axis.grid(alpha=0.18)
    for axis in (main, residual_axis, posterior_axis):
        axis.tick_params(labelbottom=False)

    figure.suptitle(
        "Scan B · NORAD 62953 / RX1 · why the row-gated recovery failed\n"
        "The satellite probability is strong, but divided among several candidate peaks per GLRT group",
        y=0.985,
    )
    figure.legend(
        handles=[
            Line2D([], [], color="black", label="Timing-adjusted orbit Doppler"),
            Line2D([], [], marker="o", color="0.72", linestyle="", label="RX1 within ±2.5 kHz"),
            Line2D(
                [],
                [],
                marker="o",
                markerfacecolor="none",
                markeredgecolor="#7B61A8",
                linestyle="",
                label="Initial-seed candidate row",
            ),
            Line2D([], [], marker="o", color="#009E73", linestyle="", label="Seed passes group gate"),
            Line2D([], [], marker="x", color="#CC3311", linestyle="", label="Seed fails group gate"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.945),
        ncol=5,
        fontsize=8,
    )
    figure.text(
        0.5,
        0.018,
        "Current gate: one row must have posterior ≥0.90. Diagnostic gate: sum 62953 posterior "
        "over candidate rows in the GLRT group, then choose the target-MAP row;\n"
        "runner-up ≤0.05, |residual| ≤150 Hz, global seed ownership preserved. "
        "Diagnostic only—no refit and not a published association rule.",
        ha="center",
        fontsize=8,
    )
    for path in output_paths:
        figure.savefig(path, dpi=180)
    plt.close(figure)


def render(output_dir=OUTPUT_DIR, source_dir=SOURCE_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = [output_dir / f"{OUTPUT_STEM}{suffix}" for suffix in (".png", ".svg")]
    receipt_path = output_dir / f"{OUTPUT_STEM}.json"
    existing = [path for path in (*output_paths, receipt_path) if path.exists()]
    if existing:
        raise FileExistsError(", ".join(map(str, existing)))

    arrays, metadata, array_path, source_receipt = load_archived_session(SESSION, source_dir)
    lookup = {int(number): column for column, number in enumerate(arrays["catalog_numbers"])}
    column = lookup[CATALOG_NUMBER]
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
        arrays,
        column,
        RECEIVER,
        seed_groups,
        owners,
        CATALOG_NUMBER,
    )
    segments = contiguous_group_segments(records)
    eligible = [
        segment
        for segment in segments
        if sum(record["seed"] for record in segment) >= MINIMUM_SEED_GROUPS
    ]
    selected = max(
        eligible,
        key=lambda segment: (
            segment[-1]["time_s"] - segment[0]["time_s"],
            len(segment),
        ),
    )
    row_tight = _row_tight_mask(arrays, column, RECEIVER, owners, CATALOG_NUMBER)
    _plot(arrays, column, initial, records, row_tight, selected, output_paths)

    seed_records = [record for record in records if record["seed"]]
    sequential_failures = Counter()
    for record in seed_records:
        if record["target_support"] < POSTERIOR_MINIMUM:
            sequential_failures["group_support_below_0.90"] += 1
        elif record["runner_up_at_best_row"] > RUNNER_UP_MAXIMUM:
            sequential_failures["best_row_runner_up_above_0.05"] += 1
        elif abs(record["best_residual_hz"]) > RESIDUAL_MAXIMUM_HZ:
            sequential_failures["best_row_residual_above_150_hz"] += 1
        else:
            sequential_failures["passes_group_aware_gate"] += 1
    maximum_rows = np.asarray(
        [record["maximum_row_posterior"] for record in seed_records], dtype=float
    )
    group_support = np.asarray(
        [record["target_support"] for record in seed_records], dtype=float
    )
    conditional_share = np.asarray(
        [record["conditional_best_row_share"] for record in seed_records], dtype=float
    )
    largest_marginal = sum(
        record["largest_group_marginal_column"] == column for record in seed_records
    )
    result = {
        "schema": "ds13-norad-62953-association-diagnostic/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "session": SESSION,
        "scan_label": "B",
        "catalog_number": CATALOG_NUMBER,
        "receiver": RECEIVER,
        "source_profile": metadata["source_profile"],
        "current_row_gate": {
            "tight_row_count": int(np.sum(row_tight)),
            "tight_seed_group_count": int(
                np.sum(np.isin(np.asarray(arrays["group"])[row_tight], list(seed_groups)))
            ),
            "segments": _row_segments(arrays, row_tight, seed_groups),
            "outcome": "no segment reaches five seed groups",
        },
        "initial_seed": {
            "proposal_count": len(initial),
            "group_count": len(seed_groups),
            "proposals": [
                {**proposal, "groups": sorted(proposal["groups"])} for proposal in initial
            ],
        },
        "group_probability_diagnostic": {
            "semantics": (
                "For one satellite, finite-set row association probabilities sum within a "
                "GLRT group to that satellite's group detection/association marginal. The "
                "target-MAP row supplies the plotted Doppler and residual."
            ),
            "seed_group_support_at_least_0.90": int(np.sum(group_support >= 0.90)),
            "seed_maximum_row_at_least_0.90": int(np.sum(maximum_rows >= 0.90)),
            "seed_target_largest_group_marginal_count": largest_marginal,
            "median_seed_group_support": float(np.median(group_support)),
            "median_seed_maximum_row_posterior": float(np.median(maximum_rows)),
            "median_seed_conditional_best_row_share": float(np.median(conditional_share)),
            "candidate_rows_per_seed_group": dict(
                sorted(Counter(record["candidate_row_count"] for record in seed_records).items())
            ),
            "sequential_seed_gate_outcomes": dict(sequential_failures),
            "segments": [_segment_summary(segment) for segment in segments],
            "selected_counterfactual_segment": _segment_summary(selected),
            "qualification": (
                "Diagnostic counterfactual only. It demonstrates the row-vs-group failure "
                "mechanism; group membership and target peak identity remain separate decisions."
            ),
        },
        "gate": {
            "target_probability_minimum": POSTERIOR_MINIMUM,
            "best_row_runner_up_maximum": RUNNER_UP_MAXIMUM,
            "absolute_best_row_residual_maximum_hz": RESIDUAL_MAXIMUM_HZ,
            "maximum_gap_s": MAX_GAP_S,
            "minimum_seed_groups": MINIMUM_SEED_GROUPS,
            "ownership": "unallocated or owned only by NORAD 62953",
        },
        "source_hashes": {
            str(array_path.resolve()): file_digest(array_path),
            str(source_receipt.resolve()): file_digest(source_receipt),
            str(bundle_path.resolve()): file_digest(bundle_path),
            str(seed_path.resolve()): file_digest(seed_path),
            str(Path(__file__).resolve()): file_digest(__file__),
        },
        "outputs": {str(path.resolve()): file_digest(path) for path in output_paths},
    }
    receipt_path.write_text(json.dumps(serializable(result), indent=2, allow_nan=False) + "\n")
    arrays.close()
    bundle.close()
    return result, output_paths, receipt_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    args = parser.parse_args(argv)
    result, outputs, receipt = render(args.output_dir, args.source_dir)
    print(
        json.dumps(
            serializable(
                {
                    "current_row_gate": result["current_row_gate"],
                    "group_probability_diagnostic": result[
                        "group_probability_diagnostic"
                    ],
                    "outputs": outputs,
                    "receipt": receipt,
                }
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
