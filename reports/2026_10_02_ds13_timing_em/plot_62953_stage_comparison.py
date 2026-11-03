"""Compare original, group-recovered, and Viterbi-smoothed NORAD 62953 tracks."""

from __future__ import annotations

import argparse
import json
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
    MINIMUM_SEED_GROUPS,
    RECEIVER,
    aggregate_groups,
    contiguous_group_segments,
)
from viterbi_62953_prototype import candidate_states, viterbi_peak_path

SESSION = SESSIONS[1]
OUTPUT_STEM = "norad-62953-rx1-three-stage-comparison"


def map_raw_seed_rows_to_family_rows(manifest, assignments):
    families = manifest["alias_grouping"]["families"]
    representatives = manifest["family_representatives"]
    if len(families) != len(representatives):
        raise ValueError("family records and representatives are not aligned")
    raw_to_family = {}
    for family_index, (family, representative) in enumerate(
        zip(families, representatives, strict=True)
    ):
        representative_rows = [
            row["input_row_index"]
            for row in family["lineage"]
            if row["candidate_id"] == family["representative_candidate_id"]
        ]
        if representative_rows != [representative]:
            raise ValueError("family order disagrees with its recorded representative")
        for row in family["lineage"]:
            raw_row = int(row["input_row_index"])
            if raw_row in raw_to_family:
                raise ValueError("raw row belongs to more than one alias family")
            raw_to_family[raw_row] = family_index

    mapped = []
    for assignment in assignments:
        rows = [raw_to_family[int(row)] for row in assignment["rows"]]
        if len(rows) != len(set(rows)):
            raise ValueError("one original proposal selects an alias family more than once")
        mapped.append(
            {
                "track_index": int(assignment["track_index"]),
                "rows": np.asarray(rows, dtype=int),
            }
        )
    return mapped


def _draw_stage(
    figure,
    slot,
    arrays,
    column,
    title,
    point_sets,
    *,
    residual_overlay=None,
):
    layout = slot.subgridspec(2, 1, height_ratios=(1.8, 1.0), hspace=0.08)
    doppler_axis = figure.add_subplot(layout[0])
    residual_axis = figure.add_subplot(layout[1], sharex=doppler_axis)
    dense_times = np.asarray(arrays["dense_times_s"], dtype=float)
    dense = np.asarray(arrays["dense_doppler_hz"], dtype=float)[:, column]
    window = (dense_times >= 168) & (dense_times <= 226)
    times = np.asarray(arrays["times_s"], dtype=float)
    doppler = np.asarray(arrays["doppler_hz"], dtype=float)[:, column]
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]

    doppler_axis.plot(dense_times[window], dense[window] / 1000, color="black", linewidth=1.4)
    for points in point_sets:
        rows = np.asarray(points["rows"], dtype=int)
        order = np.argsort(times[rows], kind="stable")
        rows = rows[order]
        options = {
            "color": points["color"],
            "marker": points.get("marker", "o"),
            "s": points.get("size", 22),
            "linewidths": points.get("linewidths", 0),
            "alpha": points.get("alpha", 0.88),
            "zorder": points.get("zorder", 4),
        }
        if points.get("connect", True):
            residual_axis.plot(
                times[rows],
                residual[rows],
                color=points["color"],
                linewidth=points.get("line_width", 0.8),
                alpha=points.get("line_alpha", 0.55),
                zorder=2,
            )
        doppler_axis.scatter(times[rows], doppler[rows] / 1000, **options)
        residual_axis.scatter(times[rows], residual[rows], **options)

    if residual_overlay is not None:
        rows = np.asarray(residual_overlay["rows"], dtype=int)
        residual_axis.scatter(
            times[rows],
            residual[rows],
            s=70,
            facecolors="none",
            edgecolors=residual_overlay.get("color", "#CC3311"),
            linewidths=1.2,
            zorder=7,
        )
        doppler_axis.scatter(
            times[rows],
            doppler[rows] / 1000,
            s=70,
            facecolors="none",
            edgecolors=residual_overlay.get("color", "#CC3311"),
            linewidths=1.2,
            zorder=7,
        )

    curve = dense[window]
    doppler_axis.set_ylim((float(np.min(curve)) - 700) / 1000, (float(np.max(curve)) + 700) / 1000)
    residual_axis.axhline(0, color="black", linewidth=0.7)
    residual_axis.axhline(150, color="#CC79A7", linestyle="--", linewidth=0.8)
    residual_axis.axhline(-150, color="#CC79A7", linestyle="--", linewidth=0.8)
    residual_axis.set_ylim(-320, 320)
    doppler_axis.set_title(title, fontsize=10)
    doppler_axis.set_ylabel("Doppler (kHz)")
    residual_axis.set_ylabel("GLRT − orbit (Hz)")
    residual_axis.set_xlabel("Receive time since capture start (s)")
    doppler_axis.tick_params(labelbottom=False)
    for axis in (doppler_axis, residual_axis):
        axis.set_xlim(168, 226)
        axis.grid(alpha=0.18)


def render(output_dir=OUTPUT_DIR, source_dir=SOURCE_DIR):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_paths = [output_dir / f"{OUTPUT_STEM}{suffix}" for suffix in (".png", ".svg")]
    receipt_path = output_dir / f"{OUTPUT_STEM}.json"
    existing = [path for path in (*image_paths, receipt_path) if path.exists()]
    if existing:
        raise FileExistsError(", ".join(map(str, existing)))

    arrays, metadata, array_path, source_receipt = load_archived_session(SESSION, source_dir)
    column = list(map(int, arrays["catalog_numbers"])).index(CATALOG_NUMBER)
    scan_dir = ROOT / "scans" / SESSION
    bundle_path = scan_dir / "bundle.npz"
    manifest_path = scan_dir / "bundle.json"
    seed_path = scan_dir / "seed.json"
    bundle = np.load(bundle_path)
    manifest = json.loads(manifest_path.read_text())
    seed = json.loads(seed_path.read_text())
    assignments = [
        assignment
        for assignment in seed["rough"]["assignments"]
        if assignment["accepted"]
        and int(assignment["catalog_number"]) == CATALOG_NUMBER
        and int(assignment["receiver"]) == RECEIVER
    ]
    original = map_raw_seed_rows_to_family_rows(manifest, assignments)
    for proposal, assignment in zip(original, assignments, strict=True):
        channels = np.unique(np.asarray(arrays["channel"])[proposal["rows"]])
        if len(channels) != 1:
            raise ValueError("original proposal crosses calibrated channel lanes")
        proposal["channel"] = int(channels[0])

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
    eligible = [
        segment
        for segment in contiguous_group_segments(records)
        if sum(record["seed"] for record in segment) >= MINIMUM_SEED_GROUPS
    ]
    segment = max(
        eligible,
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
    seed_mask = np.asarray([record["seed"] for record in segment], dtype=bool)
    changed = independent != viterbi

    figure = plt.figure(figsize=(14, 16))
    grid = figure.add_gridspec(
        3,
        1,
        left=0.085,
        right=0.98,
        bottom=0.065,
        top=0.90,
        hspace=0.36,
    )
    original_colors = {3: "#7B61A8", 4: "#009E73"}
    _draw_stage(
        figure,
        grid[0],
        arrays,
        column,
        "1 · Original rough seeds · 2 proposals / 114 groups · longest proposal 41.3 s",
        [
            {
                "rows": proposal["rows"],
                "color": original_colors[proposal["channel"]],
                "marker": "o" if proposal["channel"] == 3 else "s",
            }
            for proposal in original
        ],
    )
    _draw_stage(
        figure,
        grid[1],
        arrays,
        column,
        "2 · Group-summed prototype · 52.0 s / 153 groups · 93 seed retained + 60 fills",
        [
            {"rows": independent[seed_mask], "color": "#0072B2"},
            {"rows": independent[~seed_mask], "color": "#E69F00"},
        ],
    )
    _draw_stage(
        figure,
        grid[2],
        arrays,
        column,
        "3 · Viterbi peak path · same 52.0 s / 153 groups · 15 peak choices changed",
        [
            {
                "rows": independent,
                "color": "0.58",
                "marker": "x",
                "size": 24,
                "linewidths": 0.8,
                "alpha": 0.55,
                "connect": False,
                "zorder": 2,
            },
            {"rows": viterbi[seed_mask], "color": "#0072B2"},
            {"rows": viterbi[~seed_mask], "color": "#E69F00"},
        ],
        residual_overlay={"rows": viterbi[changed], "color": "#CC3311"},
    )
    figure.suptitle(
        "Scan B · NORAD 62953 / RX1 · original → recovered → Viterbi\n"
        "Identical sealed orbit and nuisance model in all three stages",
        y=0.985,
    )
    figure.legend(
        handles=[
            Line2D([], [], color="black", label="Timing-adjusted orbit Doppler"),
            Line2D([], [], marker="o", color="#7B61A8", linestyle="", label="Original CH3"),
            Line2D([], [], marker="s", color="#009E73", linestyle="", label="Original CH4"),
            Line2D([], [], marker="o", color="#0072B2", linestyle="", label="Original seed group"),
            Line2D([], [], marker="o", color="#E69F00", linestyle="", label="Unallocated fill"),
            Line2D([], [], marker="x", color="0.58", linestyle="", label="Pre-Viterbi MAP peak"),
            Line2D(
                [],
                [],
                marker="o",
                markerfacecolor="none",
                markeredgecolor="#CC3311",
                linestyle="",
                label="Viterbi choice changed",
            ),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.945),
        ncol=4,
        fontsize=8,
    )
    figure.text(
        0.5,
        0.018,
        "Stage 1 uses the recorded seed rows mapped through sealed alias-family lineage. "
        "Stage 2 fixes the rejection by gating summed satellite support per GLRT group.\n"
        "Stage 3 keeps every Stage-2 group and changes only the selected peak in 15 groups; "
        "red rings mark those changes. No refit.",
        ha="center",
        fontsize=8,
    )
    for path in image_paths:
        figure.savefig(path, dpi=180)
    plt.close(figure)

    original_rows = np.concatenate([proposal["rows"] for proposal in original])
    result = {
        "schema": "ds13-norad-62953-three-stage-comparison/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "session": SESSION,
        "scan_label": "B",
        "catalog_number": CATALOG_NUMBER,
        "receiver": RECEIVER,
        "source_profile": metadata["source_profile"],
        "stages": {
            "original": {
                "proposal_count": len(original),
                "group_count": len(original_rows),
                "proposal_group_counts": [len(proposal["rows"]) for proposal in original],
                "proposal_channels": [proposal["channel"] for proposal in original],
                "longest_duration_s": max(proposal["duration_s"] for proposal in initial),
                "absolute_residual_median_hz": float(
                    np.median(np.abs(residual[original_rows]))
                ),
                "absolute_residual_p95_hz": float(
                    np.quantile(np.abs(residual[original_rows]), 0.95)
                ),
            },
            "group_summed_prototype": {
                "duration_s": segment[-1]["time_s"] - segment[0]["time_s"],
                "group_count": len(segment),
                "seed_group_count": int(np.sum(seed_mask)),
                "unallocated_group_count": int(np.sum(~seed_mask)),
                "absolute_residual_median_hz": float(
                    np.median(np.abs(residual[independent]))
                ),
                "absolute_residual_p95_hz": float(
                    np.quantile(np.abs(residual[independent]), 0.95)
                ),
            },
            "viterbi": {
                "duration_s": segment[-1]["time_s"] - segment[0]["time_s"],
                "group_count": len(segment),
                "membership_changed_count": 0,
                "peak_choice_changed_count": int(np.sum(changed)),
                "absolute_residual_median_hz": float(
                    np.median(np.abs(residual[viterbi]))
                ),
                "absolute_residual_p95_hz": float(
                    np.quantile(np.abs(residual[viterbi]), 0.95)
                ),
            },
        },
        "source_hashes": {
            str(array_path.resolve()): file_digest(array_path),
            str(source_receipt.resolve()): file_digest(source_receipt),
            str(bundle_path.resolve()): file_digest(bundle_path),
            str(manifest_path.resolve()): file_digest(manifest_path),
            str(seed_path.resolve()): file_digest(seed_path),
            str(Path(__file__).resolve()): file_digest(__file__),
        },
        "outputs": {str(path.resolve()): file_digest(path) for path in image_paths},
        "qualification": (
            "Development-data diagnostic. Stage 2 is a group-membership counterfactual; "
            "Stage 3 uses an unvalidated continuity weight for peak identity only."
        ),
    }
    receipt_path.write_text(json.dumps(serializable(result), indent=2, allow_nan=False) + "\n")
    arrays.close()
    bundle.close()
    return result, image_paths, receipt_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    args = parser.parse_args(argv)
    result, images, receipt = render(args.output_dir, args.source_dir)
    print(json.dumps(serializable({"stages": result["stages"], "images": images, "receipt": receipt}), indent=2))


if __name__ == "__main__":
    main()
