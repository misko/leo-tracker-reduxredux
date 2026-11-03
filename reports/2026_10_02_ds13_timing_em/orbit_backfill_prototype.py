"""Seed-preserving orbit backfill over stored DS13 GLRT peak groups."""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from plot_all_glrt_doppler_overlay import (
    ROOT,
    SESSIONS,
    SOURCE_DIR,
    file_digest,
    load_archived_session,
    serializable,
)

OUTPUT_DIR = ROOT / "orbit-backfill-prototype"
RETRIEVAL_GATE_HZ = 2_500.0
POSTERIOR_MINIMUM = 0.90
RUNNER_UP_MAXIMUM = 0.05
RESIDUAL_MAXIMUM_HZ = 150.0
MAX_GAP_S = 3.0
MINIMUM_SEED_GROUPS = 5


def build_initial_inventory(seed, raw_group, raw_times, raw_channel, selected_catalogs):
    raw_group = np.asarray(raw_group)
    raw_times = np.asarray(raw_times, dtype=float)
    raw_channel = np.asarray(raw_channel)
    if raw_group.shape != raw_times.shape or raw_channel.shape != raw_times.shape:
        raise ValueError("raw bundle arrays are not aligned")
    owners = defaultdict(set)
    proposals = defaultdict(list)
    selected_catalogs = {int(value) for value in selected_catalogs}
    for assignment in seed["rough"]["assignments"]:
        if not assignment["accepted"]:
            continue
        rows = np.asarray(assignment["rows"], dtype=int)
        if rows.ndim != 1 or not len(rows) or np.any(rows < 0) or np.any(rows >= len(raw_group)):
            raise ValueError("initial proposal rows are outside the raw bundle")
        number = int(assignment["catalog_number"])
        receiver = int(assignment["receiver"])
        groups = {int(value) for value in raw_group[rows]}
        for group in groups:
            owners[group].add(number)
        if number not in selected_catalogs:
            continue
        channels = sorted({int(value) for value in raw_channel[rows]})
        proposals[(number, receiver)].append(
            {
                "track_index": int(assignment["track_index"]),
                "groups": groups,
                "group_count": len(groups),
                "start_s": float(np.min(raw_times[rows])),
                "end_s": float(np.max(raw_times[rows])),
                "duration_s": float(np.ptp(raw_times[rows])),
                "channels": channels,
            }
        )
    return dict(owners), dict(proposals)


def _segments(times_s, rows, max_gap_s=MAX_GAP_S):
    rows = np.asarray(rows, dtype=int)
    if not len(rows):
        return []
    rows = rows[np.argsort(times_s[rows], kind="stable")]
    cuts = np.flatnonzero(np.diff(times_s[rows]) > max_gap_s) + 1
    return [segment for segment in np.split(rows, cuts) if len(segment)]


def recover_track(
    arrays,
    column,
    receiver,
    initial_proposals,
    owners,
    *,
    minimum_seed_groups=MINIMUM_SEED_GROUPS,
):
    number = int(arrays["catalog_numbers"][column])
    times = np.asarray(arrays["times_s"], dtype=float)
    groups = np.asarray(arrays["group"], dtype=int)
    row_receiver = np.asarray(arrays["receiver"], dtype=int)
    posterior = np.asarray(arrays["posterior"], dtype=float)
    residual = np.abs(np.asarray(arrays["residual_hz"], dtype=float)[:, column])
    competitors = np.delete(posterior, column, axis=1)
    runner_up = np.max(competitors, axis=1) if competitors.shape[1] else np.zeros(len(times))
    seed_groups = set().union(*(proposal["groups"] for proposal in initial_proposals))
    allowed = np.fromiter(
        (
            not owners.get(int(group), set()) or owners.get(int(group), set()) == {number}
            for group in groups
        ),
        dtype=bool,
        count=len(groups),
    )
    same_receiver = row_receiver == receiver
    retrieved = same_receiver & (residual <= RETRIEVAL_GATE_HZ)
    safe_retrieved = retrieved & allowed
    tight = (
        safe_retrieved
        & (posterior[:, column] >= POSTERIOR_MINIMUM)
        & (runner_up <= RUNNER_UP_MAXIMUM)
        & (residual <= RESIDUAL_MAXIMUM_HZ)
    )
    contested_tight = (
        retrieved
        & ~allowed
        & (posterior[:, column] >= POSTERIOR_MINIMUM)
        & (runner_up <= RUNNER_UP_MAXIMUM)
        & (residual <= RESIDUAL_MAXIMUM_HZ)
    )
    eligible = []
    for segment in _segments(times, np.flatnonzero(tight)):
        support = sum(int(groups[row]) in seed_groups for row in segment)
        if support >= minimum_seed_groups:
            eligible.append((segment, support))
    baseline_longest = max(proposal["duration_s"] for proposal in initial_proposals)
    base = {
        "catalog_number": number,
        "receiver": receiver,
        "initial_proposal_count": len(initial_proposals),
        "initial_seed_group_count": len(seed_groups),
        "initial_longest_duration_s": baseline_longest,
        "initial_envelope_start_s": min(proposal["start_s"] for proposal in initial_proposals),
        "initial_envelope_end_s": max(proposal["end_s"] for proposal in initial_proposals),
        "initial_proposals": initial_proposals,
        "retrieved_row_count": int(np.sum(retrieved)),
        "safe_retrieved_row_count": int(np.sum(safe_retrieved)),
        "tight_safe_row_count": int(np.sum(tight)),
        "tight_contested_row_count": int(np.sum(contested_tight)),
    }
    if not eligible:
        return {
            **base,
            "status": "no-seed-anchored-tight-segment",
            "selected_rows": np.empty(0, dtype=int),
        }

    def rank(item):
        segment, support = item
        return (
            float(times[segment[-1]] - times[segment[0]]),
            len(segment),
            support,
            -float(times[segment[0]]),
        )

    selected, seed_support = max(eligible, key=rank)
    selected_groups = [int(groups[row]) for row in selected]
    if len(set(selected_groups)) != len(selected_groups):
        raise ValueError("recovered track selected multiple peaks from one GLRT group")
    selected_owners = [owners.get(group, set()) for group in selected_groups]
    unallocated = np.asarray([not value for value in selected_owners], dtype=bool)
    seed_owned = np.asarray([value == {number} for value in selected_owners], dtype=bool)
    if np.any(~(unallocated | seed_owned)):
        raise ValueError("safe recovery selected a group owned by another initial identity")
    selected_residual = residual[selected]
    selected_posterior = posterior[selected, column]
    selected_runner_up = runner_up[selected]
    duration = float(times[selected[-1]] - times[selected[0]])
    return {
        **base,
        "status": "recovered",
        "selected_rows": selected,
        "selected_groups": selected_groups,
        "selected_start_s": float(times[selected[0]]),
        "selected_end_s": float(times[selected[-1]]),
        "selected_duration_s": duration,
        "duration_ratio_to_longest_initial": duration / baseline_longest,
        "selected_group_count": len(selected),
        "selected_seed_support_count": seed_support,
        "selected_seed_owned_count": int(np.sum(seed_owned)),
        "selected_unallocated_count": int(np.sum(unallocated)),
        "residual_median_hz": float(np.median(selected_residual)),
        "residual_p95_hz": float(np.quantile(selected_residual, 0.95)),
        "posterior_minimum": float(np.min(selected_posterior)),
        "runner_up_maximum": float(np.max(selected_runner_up)),
    }


def run_scan(session, scan_label, source_dir=SOURCE_DIR):
    started = time.monotonic()
    arrays, metadata, array_path, source_receipt = load_archived_session(session, source_dir)
    scan_dir = ROOT / "scans" / session
    bundle_path = scan_dir / "bundle.npz"
    seed_path = scan_dir / "seed.json"
    bundle = np.load(bundle_path)
    seed = json.loads(seed_path.read_text())
    selected_catalogs = [int(value) for value in arrays["catalog_numbers"]]
    owners, proposals = build_initial_inventory(
        seed,
        bundle["group"],
        bundle["times"],
        bundle["channel"],
        selected_catalogs,
    )
    lookup = {int(number): column for column, number in enumerate(arrays["catalog_numbers"])}
    tracks = []
    for (number, receiver), initial in sorted(proposals.items()):
        tracks.append(recover_track(arrays, lookup[number], receiver, initial, owners))
    selected_claims = [
        int(row)
        for track in tracks
        if track["status"] == "recovered"
        for row in track["selected_rows"]
    ]
    if len(selected_claims) != len(set(selected_claims)):
        raise ValueError("one stored GLRT peak was recovered into multiple tracks")
    recovered = [track for track in tracks if track["status"] == "recovered"]
    full_edge_count = len(arrays["times_s"]) * len(tracks)
    retrieved_edge_count = sum(track["retrieved_row_count"] for track in tracks)
    safe_retrieved_edge_count = sum(track["safe_retrieved_row_count"] for track in tracks)
    tight_safe_edge_count = sum(track["tight_safe_row_count"] for track in tracks)
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
        "selected_catalog_count": len(selected_catalogs),
        "seeded_track_count": len(tracks),
        "recovered_track_count": len(recovered),
        "failed_track_count": len(tracks) - len(recovered),
        "full_row_track_edge_count": full_edge_count,
        "retrieved_edge_count": retrieved_edge_count,
        "safe_retrieved_edge_count": safe_retrieved_edge_count,
        "tight_safe_edge_count": tight_safe_edge_count,
        "retrieved_fraction_of_full": retrieved_edge_count / full_edge_count,
        "selected_group_count": sum(track["selected_group_count"] for track in recovered),
        "selected_seed_owned_count": sum(track["selected_seed_owned_count"] for track in recovered),
        "selected_unallocated_count": sum(
            track["selected_unallocated_count"] for track in recovered
        ),
        "tight_contested_row_count": sum(track["tight_contested_row_count"] for track in tracks),
        "tracks": tracks,
        "association_elapsed_s": time.monotonic() - started,
    }
    arrays.close()
    bundle.close()
    return result


def _plain_track(track):
    plain = {key: value for key, value in track.items() if key != "selected_rows"}
    plain["initial_proposals"] = [
        {**proposal, "groups": sorted(proposal["groups"])}
        for proposal in track["initial_proposals"]
    ]
    return plain


def write_csv(results, path):
    fields = [
        "scan_label",
        "catalog_number",
        "receiver",
        "status",
        "initial_proposal_count",
        "initial_seed_group_count",
        "initial_longest_duration_s",
        "selected_start_s",
        "selected_end_s",
        "selected_duration_s",
        "duration_ratio_to_longest_initial",
        "selected_group_count",
        "selected_seed_owned_count",
        "selected_unallocated_count",
        "retrieved_row_count",
        "safe_retrieved_row_count",
        "tight_safe_row_count",
        "tight_contested_row_count",
        "residual_p95_hz",
        "posterior_minimum",
        "runner_up_maximum",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for result in results:
        for track in result["tracks"]:
            writer.writerow({"scan_label": result["scan_label"], **track})
    path.write_text(stream.getvalue())


def plot_timeline(result, path_stem, source_dir=SOURCE_DIR):
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
    arrays, _, _, _ = load_archived_session(result["session"], source_dir=source_dir)
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
        selected_rows = track["selected_rows"]
        times = arrays["times_s"][selected_rows]
        groups = arrays["group"][selected_rows]
        seed_groups = set().union(
            *(set(proposal["groups"]) for proposal in track["initial_proposals"])
        )
        seed = np.asarray([int(group) in seed_groups for group in groups])
        axis.plot(
            [track["selected_start_s"], track["selected_end_s"]],
            [y - 0.10, y - 0.10],
            color="#0072B2",
            linewidth=2,
            zorder=2,
        )
        axis.scatter(times[seed], np.full(np.sum(seed), y - 0.10), color="#0072B2", s=13)
        axis.scatter(
            times[~seed],
            np.full(np.sum(~seed), y - 0.10),
            color="#E69F00",
            s=13,
        )
    arrays.close()
    axis.set_yticks(np.arange(len(tracks)), labels=labels)
    axis.set_xlim(0, 300)
    axis.set_ylim(-0.65, len(tracks) - 0.35)
    axis.invert_yaxis()
    axis.set_xlabel("Receive time since capture start (s)")
    axis.set_title(
        f"DS13 scan {result['scan_label']} · seed-preserving orbit backfill\n"
        f"{result['recovered_track_count']}/{result['seeded_track_count']} seeded tracks "
        f"recovered; {result['selected_unallocated_count']} unallocated groups added"
    )
    axis.grid(axis="x", alpha=0.2)
    axis.legend(
        handles=[
            Line2D([], [], color="0.62", linewidth=5, label="Initial proposals"),
            Line2D([], [], color="#0072B2", linewidth=2, marker="o", label="Seed-owned"),
            Line2D([], [], color="#E69F00", linewidth=0, marker="o", label="Unallocated fill"),
            Line2D([], [], color="#CC3311", linewidth=0, marker="x", label="No tight segment"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=4,
        fontsize=8,
    )
    figure.tight_layout(rect=(0, 0.05, 1, 1))
    outputs = []
    for extension in (".png", ".svg"):
        output = path_stem.with_suffix(extension)
        figure.savefig(output, dpi=170)
        outputs.append(output)
    plt.close(figure)
    return outputs


def summary_markdown(results, elapsed_s):
    lines = [
        "# Seed-preserving orbit backfill prototype",
        "",
        "This recorded-corpus replay uses sealed DS13 reference-position orbit/posterior arrays. "
        "It tests sparse membership recovery, not a standalone blind or streaming orbit fit.",
        "",
        "New membership is restricted to GLRT groups unused by every accepted initial proposal. "
        "Groups owned by another initial identity are never reassigned.",
        "",
        "| Scan | Recovered / seeded | Dense edges | Retrieved edges | Selected groups | "
        "Unallocated fill | Tight contested excluded |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result['scan_label']} | {result['recovered_track_count']} / "
            f"{result['seeded_track_count']} | {result['full_row_track_edge_count']} | "
            f"{result['retrieved_edge_count']} | {result['selected_group_count']} | "
            f"{result['selected_unallocated_count']} | "
            f"{result['tight_contested_row_count']} |"
        )
    lines += [
        "",
        f"Prototype wall time: {elapsed_s:.3f} seconds.",
        "",
        "Gate: ±2.5 kHz retrieval, posterior ≥0.90, runner-up ≤0.05, "
        "|residual| ≤150 Hz, maximum gap 3 seconds, and at least five original seed groups.",
    ]
    return "\n".join(lines) + "\n"


def run(output_dir=OUTPUT_DIR, source_dir=SOURCE_DIR):
    started = time.monotonic()
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    output_dir.mkdir(parents=True)
    results = [
        run_scan(session, "AB"[index], source_dir=source_dir)
        for index, session in enumerate(SESSIONS)
    ]
    artifacts = []
    for result in results:
        artifacts.extend(
            plot_timeline(
                result,
                output_dir / f"scan-{result['scan_label'].lower()}-timeline",
                source_dir=source_dir,
            )
        )
    csv_path = output_dir / "tracks.csv"
    write_csv(results, csv_path)
    artifacts.append(csv_path)
    elapsed_s = time.monotonic() - started
    readme = output_dir / "README.md"
    readme.write_text(summary_markdown(results, elapsed_s))
    artifacts.append(readme)
    result_path = output_dir / "summary.json"
    payload = {
        "schema": "ds13-seed-preserving-orbit-backfill/v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "elapsed_s": elapsed_s,
        "configuration": {
            "retrieval_gate_hz": RETRIEVAL_GATE_HZ,
            "posterior_minimum": POSTERIOR_MINIMUM,
            "runner_up_maximum": RUNNER_UP_MAXIMUM,
            "absolute_residual_maximum_hz": RESIDUAL_MAXIMUM_HZ,
            "maximum_gap_s": MAX_GAP_S,
            "minimum_seed_groups": MINIMUM_SEED_GROUPS,
            "new_membership": "groups unowned by every accepted initial proposal",
            "contested_initial_groups_reassigned": False,
        },
        "scope": "Recorded-corpus association replay using sealed reference-position "
        "posteriors and orbit residuals. No RF, GLRT rerun, orbit fit, or nuisance refit.",
        "scans": [
            {**result, "tracks": [_plain_track(track) for track in result["tracks"]]}
            for result in results
        ],
        "artifact_sha256": {str(path.resolve()): file_digest(path) for path in artifacts},
    }
    result_path.write_text(json.dumps(serializable(payload), indent=2, allow_nan=False) + "\n")
    return payload, result_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    args = parser.parse_args(argv)
    payload, result_path = run(output_dir=args.output_dir, source_dir=args.source_dir)
    print(
        json.dumps(
            {
                "output": str(result_path.parent),
                "summary": str(result_path),
                "elapsed_s": payload["elapsed_s"],
                "scans": [
                    {
                        "scan": result["scan_label"],
                        "recovered": result["recovered_track_count"],
                        "seeded": result["seeded_track_count"],
                        "unallocated_added": result["selected_unallocated_count"],
                    }
                    for result in payload["scans"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
