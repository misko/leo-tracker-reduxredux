"""Run and plot group-summed orbit backfill with optional Viterbi peak selection."""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from orbit_backfill_prototype import (
    MAX_GAP_S,
    MINIMUM_SEED_GROUPS,
    OUTPUT_DIR,
    ROOT,
    SESSIONS,
    SOURCE_DIR,
    build_initial_inventory,
    file_digest,
    load_archived_session,
    serializable,
)
from plot_62953_diagnostic import aggregate_groups, contiguous_group_segments
from viterbi_62953_prototype import candidate_states, viterbi_peak_path

OUTPUT_PREFIX = "group-summed-orbit-backfill"


def recover_group_track(arrays, column, receiver, initial_proposals, owners):
    number = int(arrays["catalog_numbers"][column])
    seed_groups = set().union(*(proposal["groups"] for proposal in initial_proposals))
    records = aggregate_groups(
        arrays,
        column,
        receiver,
        seed_groups,
        owners,
        number,
    )
    eligible = [
        segment
        for segment in contiguous_group_segments(records)
        if sum(record["seed"] for record in segment) >= MINIMUM_SEED_GROUPS
    ]
    base = {
        "catalog_number": number,
        "receiver": receiver,
        "initial_proposal_count": len(initial_proposals),
        "initial_seed_group_count": len(seed_groups),
        "initial_longest_duration_s": max(
            proposal["duration_s"] for proposal in initial_proposals
        ),
        "initial_envelope_start_s": min(
            proposal["start_s"] for proposal in initial_proposals
        ),
        "initial_envelope_end_s": max(
            proposal["end_s"] for proposal in initial_proposals
        ),
        "initial_proposals": initial_proposals,
    }
    if not eligible:
        return {
            **base,
            "status": "no-seed-anchored-group-tight-segment",
            "selected_records": [],
            "independent_rows": np.empty(0, dtype=int),
            "viterbi_rows": np.empty(0, dtype=int),
        }

    selected = max(
        eligible,
        key=lambda segment: (
            segment[-1]["time_s"] - segment[0]["time_s"],
            len(segment),
            sum(record["seed"] for record in segment),
            -segment[0]["time_s"],
        ),
    )
    states = candidate_states(arrays, column, receiver, selected)
    posterior = np.asarray(arrays["posterior"], dtype=float)
    residual = np.asarray(arrays["residual_hz"], dtype=float)[:, column]
    support = np.asarray([record["target_support"] for record in selected], dtype=float)
    independent = np.asarray(
        [int(rows[np.argmax(posterior[rows, column])]) for rows in states], dtype=int
    )
    viterbi = viterbi_peak_path(states, posterior, residual, column, support)
    changed = independent != viterbi
    seed_owned = sum(record["owners"] == [number] for record in selected)
    unallocated = sum(not record["owners"] for record in selected)
    if seed_owned + unallocated != len(selected):
        raise ValueError("group-summed recovery selected a group with conflicting ownership")
    duration = selected[-1]["time_s"] - selected[0]["time_s"]
    return {
        **base,
        "status": "recovered",
        "selected_records": selected,
        "independent_rows": independent,
        "viterbi_rows": viterbi,
        "candidate_state_counts": [len(rows) for rows in states],
        "selected_start_s": selected[0]["time_s"],
        "selected_end_s": selected[-1]["time_s"],
        "selected_duration_s": duration,
        "duration_ratio_to_longest_initial": duration / base["initial_longest_duration_s"],
        "selected_group_count": len(selected),
        "selected_seed_support_count": sum(record["seed"] for record in selected),
        "selected_seed_owned_count": seed_owned,
        "selected_unallocated_count": unallocated,
        "viterbi_changed_count": int(np.sum(changed)),
        "independent_absolute_residual_p95_hz": float(
            np.quantile(np.abs(residual[independent]), 0.95)
        ),
        "viterbi_absolute_residual_p95_hz": float(
            np.quantile(np.abs(residual[viterbi]), 0.95)
        ),
    }


def _collision_summary(tracks, row_field):
    claims = defaultdict(list)
    for track in tracks:
        for row in track[row_field]:
            claims[int(row)].append((track["catalog_number"], track["receiver"]))
    collisions = {row: claimants for row, claimants in claims.items() if len(claimants) > 1}
    return {
        "colliding_row_count": len(collisions),
        "excess_claim_count": sum(len(claimants) - 1 for claimants in collisions.values()),
        "collisions": collisions,
    }


def run_scan(session, scan_label, source_dir=SOURCE_DIR):
    started = time.monotonic()
    arrays, metadata, array_path, source_receipt = load_archived_session(session, source_dir)
    scan_dir = ROOT / "scans" / session
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
    lookup = {int(number): column for column, number in enumerate(arrays["catalog_numbers"])}
    tracks = [
        recover_group_track(arrays, lookup[number], receiver, initial, owners)
        for (number, receiver), initial in sorted(proposals.items())
    ]
    recovered = [track for track in tracks if track["status"] == "recovered"]
    independent_collisions = _collision_summary(recovered, "independent_rows")
    viterbi_collisions = _collision_summary(recovered, "viterbi_rows")
    result = {
        "session": session,
        "scan_label": scan_label,
        "source_profile": metadata["source_profile"],
        "source_hashes": {
            str(array_path.resolve()): file_digest(array_path),
            str(source_receipt.resolve()): file_digest(source_receipt),
            str(bundle_path.resolve()): file_digest(bundle_path),
            str(seed_path.resolve()): file_digest(seed_path),
            str(Path(__file__).resolve()): file_digest(__file__),
        },
        "seeded_track_count": len(tracks),
        "recovered_track_count": len(recovered),
        "failed_track_count": len(tracks) - len(recovered),
        "selected_group_count": sum(track["selected_group_count"] for track in recovered),
        "selected_seed_owned_count": sum(
            track["selected_seed_owned_count"] for track in recovered
        ),
        "selected_unallocated_count": sum(
            track["selected_unallocated_count"] for track in recovered
        ),
        "viterbi_changed_count": sum(track["viterbi_changed_count"] for track in recovered),
        "independent_peak_collisions": independent_collisions,
        "viterbi_peak_collisions": viterbi_collisions,
        "tracks": tracks,
        "association_elapsed_s": time.monotonic() - started,
    }
    arrays.close()
    bundle.close()
    return result


def _plain_track(track):
    omitted = {"selected_records", "independent_rows", "viterbi_rows"}
    plain = {key: value for key, value in track.items() if key not in omitted}
    plain["initial_proposals"] = [
        {**proposal, "groups": sorted(proposal["groups"])}
        for proposal in track["initial_proposals"]
    ]
    return plain


def _plot_timeline(result, arrays, path_stem, *, viterbi):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    tracks = sorted(
        result["tracks"],
        key=lambda track: (
            track.get("selected_start_s", track["initial_envelope_start_s"]),
            track["catalog_number"],
            track["receiver"],
        ),
    )
    figure, axis = plt.subplots(figsize=(14, max(6.0, 0.62 * len(tracks) + 2.2)))
    labels = []
    for y, track in enumerate(tracks):
        labels.append(f"{track['catalog_number']} / RX{track['receiver']}")
        for proposal in track["initial_proposals"]:
            axis.plot(
                [proposal["start_s"], proposal["end_s"]],
                [y + 0.13, y + 0.13],
                color="0.62",
                linewidth=5,
                solid_capstyle="round",
            )
        if track["status"] != "recovered":
            axis.scatter(
                track["initial_envelope_end_s"] + 2,
                y,
                marker="x",
                color="#CC3311",
                s=48,
                zorder=5,
            )
            continue
        records = track["selected_records"]
        times = np.asarray([record["time_s"] for record in records], dtype=float)
        seed_owned = np.asarray(
            [record["owners"] == [track["catalog_number"]] for record in records],
            dtype=bool,
        )
        axis.plot(
            [track["selected_start_s"], track["selected_end_s"]],
            [y - 0.10, y - 0.10],
            color="#0072B2",
            linewidth=2,
            zorder=2,
        )
        axis.scatter(
            times[seed_owned],
            np.full(np.sum(seed_owned), y - 0.10),
            color="#0072B2",
            s=13,
            zorder=4,
        )
        axis.scatter(
            times[~seed_owned],
            np.full(np.sum(~seed_owned), y - 0.10),
            color="#E69F00",
            s=13,
            zorder=4,
        )
        if viterbi:
            changed = track["independent_rows"] != track["viterbi_rows"]
            axis.scatter(
                times[changed],
                np.full(np.sum(changed), y - 0.10),
                s=54,
                facecolors="none",
                edgecolors="#CC3311",
                linewidths=1.1,
                zorder=6,
            )

    axis.set_yticks(np.arange(len(tracks)), labels=labels)
    axis.set_xlim(0, 300)
    axis.set_ylim(-0.75, len(tracks) - 0.25)
    axis.invert_yaxis()
    axis.set_xlabel("Receive time since capture start (s)")
    axis.grid(axis="x", alpha=0.20)
    if viterbi:
        subtitle = (
            f"{result['recovered_track_count']}/{result['seeded_track_count']} seeded tracks "
            f"recovered; {result['selected_unallocated_count']} unallocated memberships added; "
            f"{result['viterbi_changed_count']} peak choices changed"
        )
        method = "group-summed backfill + Viterbi peak selection"
    else:
        subtitle = (
            f"{result['recovered_track_count']}/{result['seeded_track_count']} seeded tracks "
            f"recovered; {result['selected_unallocated_count']} unallocated memberships added"
        )
        method = "group-summed orbit backfill"
    axis.set_title(f"DS13 scan {result['scan_label']} · {method}\n{subtitle}")
    handles = [
        Line2D([], [], color="0.62", linewidth=5, label="Initial proposals"),
        Line2D([], [], marker="o", color="#0072B2", label="Seed-owned"),
        Line2D([], [], marker="o", color="#E69F00", linestyle="", label="Unallocated fill"),
        Line2D([], [], marker="x", color="#CC3311", linestyle="", label="No group-tight segment"),
    ]
    if viterbi:
        handles.append(
            Line2D(
                [],
                [],
                marker="o",
                markerfacecolor="none",
                markeredgecolor="#CC3311",
                linestyle="",
                label="Viterbi peak changed",
            )
        )
    figure.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.015),
        ncol=len(handles),
        fontsize=8,
    )
    figure.text(
        0.5,
        0.045,
        "Membership: summed satellite posterior per GLRT group ≥0.90; target-MAP residual ≤150 Hz; "
        "runner-up ≤0.05; gap ≤3 s; global initial ownership preserved."
        + (
            " Red rings change peak identity only; membership is identical to the group-summed plot."
            if viterbi
            else ""
        ),
        ha="center",
        fontsize=7.5,
    )
    figure.tight_layout(rect=(0.0, 0.08, 1.0, 0.98))
    outputs = [path_stem.with_suffix(suffix) for suffix in (".png", ".svg")]
    for path in outputs:
        figure.savefig(path, dpi=180)
    plt.close(figure)
    return outputs


def write_memberships(results, path):
    fields = [
        "scan_label",
        "catalog_number",
        "receiver",
        "group",
        "time_s",
        "channel",
        "seed_group",
        "owner_state",
        "target_group_support",
        "eligible_candidate_count",
        "independent_row",
        "viterbi_row",
        "viterbi_changed",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for result in results:
        for track in result["tracks"]:
            if track["status"] != "recovered":
                continue
            for record, candidate_count, independent, viterbi in zip(
                track["selected_records"],
                track["candidate_state_counts"],
                track["independent_rows"],
                track["viterbi_rows"],
                strict=True,
            ):
                writer.writerow(
                    {
                        "scan_label": result["scan_label"],
                        "catalog_number": track["catalog_number"],
                        "receiver": track["receiver"],
                        "group": record["group"],
                        "time_s": record["time_s"],
                        "channel": record["channel"],
                        "seed_group": record["seed"],
                        "owner_state": "seed-owned" if record["owners"] else "unallocated",
                        "target_group_support": record["target_support"],
                        "eligible_candidate_count": candidate_count,
                        "independent_row": int(independent),
                        "viterbi_row": int(viterbi),
                        "viterbi_changed": bool(independent != viterbi),
                    }
                )
    path.write_text(stream.getvalue())


def run(output_dir=OUTPUT_DIR, source_dir=SOURCE_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / f"{OUTPUT_PREFIX}-receipt.json"
    membership_path = output_dir / f"{OUTPUT_PREFIX}-memberships.csv"
    planned = [receipt_path, membership_path]
    for label in "ab":
        for suffix in (".png", ".svg"):
            planned.append(output_dir / f"{OUTPUT_PREFIX}-scan-{label}{suffix}")
            planned.append(output_dir / f"{OUTPUT_PREFIX}-viterbi-scan-{label}{suffix}")
    existing = [path for path in planned if path.exists()]
    if existing:
        raise FileExistsError(", ".join(map(str, existing)))

    results = [
        run_scan(session, "AB"[index], source_dir=source_dir)
        for index, session in enumerate(SESSIONS)
    ]
    output_paths = []
    for result in results:
        arrays, _, _, _ = load_archived_session(result["session"], source_dir)
        label = result["scan_label"].lower()
        output_paths.extend(
            _plot_timeline(
                result,
                arrays,
                output_dir / f"{OUTPUT_PREFIX}-scan-{label}",
                viterbi=False,
            )
        )
        output_paths.extend(
            _plot_timeline(
                result,
                arrays,
                output_dir / f"{OUTPUT_PREFIX}-viterbi-scan-{label}",
                viterbi=True,
            )
        )
        arrays.close()
    write_memberships(results, membership_path)
    receipt = {
        "schema": "ds13-group-summed-viterbi-backfill/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "membership_method": (
            "Sum finite-set row association probabilities by GLRT group and satellite; gate "
            "group support at 0.90, target-MAP row runner-up at 0.05 and residual at 150 Hz; "
            "retain only globally unallocated or same-satellite seed-owned groups."
        ),
        "viterbi_method": (
            "Membership fixed. Choose one eligible peak per group with emission "
            "-log(row posterior/group support) and transition 0.25*Huber(delta residual/100 Hz)."
        ),
        "scans": [
            {
                **{key: value for key, value in result.items() if key != "tracks"},
                "tracks": [_plain_track(track) for track in result["tracks"]],
            }
            for result in results
        ],
        "qualification": (
            "Development-data prototype, not independent validation. Group membership is a new "
            "counterfactual extraction from sealed posteriors. Viterbi continuity weight is not "
            "label-validated. Zero row collisions are required and reported."
        ),
        "outputs": {
            str(path.resolve()): file_digest(path)
            for path in (*output_paths, membership_path)
        },
    }
    receipt_path.write_text(json.dumps(serializable(receipt), indent=2, allow_nan=False) + "\n")
    return results, output_paths, membership_path, receipt_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    args = parser.parse_args(argv)
    results, outputs, memberships, receipt = run(args.output_dir, args.source_dir)
    print(
        json.dumps(
            serializable(
                {
                    "scans": [
                        {
                            "scan_label": result["scan_label"],
                            "recovered": result["recovered_track_count"],
                            "seeded": result["seeded_track_count"],
                            "unallocated": result["selected_unallocated_count"],
                            "viterbi_changed": result["viterbi_changed_count"],
                            "independent_collisions": result[
                                "independent_peak_collisions"
                            ]["colliding_row_count"],
                            "viterbi_collisions": result["viterbi_peak_collisions"][
                                "colliding_row_count"
                            ],
                        }
                        for result in results
                    ],
                    "outputs": outputs,
                    "memberships": memberships,
                    "receipt": receipt,
                }
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
