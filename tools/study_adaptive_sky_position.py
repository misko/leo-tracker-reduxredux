"""Reproducible RF-only wide-prior position study; independent of known-site matches."""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from replay_regional_doppler import run, summarize_grid, write_json

from leo.analysis.persistent_hop_trajectory import (
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.analysis.research.regional_doppler import Grid
from leo.application.scanner_trajectory import (
    project_scanner_candidates,
    timing_is_qualified_for_tle,
)
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.errors import BundleNotFoundError
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

WIDTH_KM = 9000 * 1.609344
CENTER = (39.7392, -104.9903)


def export_one(task):
    sid, root, output = task
    sources = ScannerTrackingInputStore(root)
    try:
        source = sources.load(sid)
        if not timing_is_qualified_for_tle(source.timing):
            raise ValueError("UTC unqualified")
        start = source.timing.first_sample_estimate_utc_ns
        trajectory = reconstruct_persistent_hop_trajectories(project_scanner_candidates(source))
        # Only the RF-leading hypothesis; alternatives may repeat the same observations.
        hypothesis = trajectory.hypotheses[0]
        by_id = {t.tracklet_id: t for t in trajectory.tracklets}
        selected = {}
        for tid in hypothesis.tracklet_ids:
            t = by_id[tid]
            rows = sorted(
                persistent_hop_tracklet_graph(hypothesis, tid).observations,
                key=lambda r: r.support_center_utc_ns,
            )
            span = (rows[-1].support_center_utc_ns - rows[0].support_center_utc_ns) / 1e9
            if len(rows) < 14 or span < 7:
                continue
            lane = (t.lane_key[0], t.lane_key[1].value)
            if lane not in selected or span > selected[lane][0]:
                selected[lane] = (span, tid, rows)
        series = []
        for (channel, edge), (_, tid, rows) in sorted(selected.items()):
            series.append(
                dict(
                    tracklet_id=tid,
                    channel=channel,
                    edge=edge,
                    actual_rf_hz=11.2e9,
                    t_s=[(r.support_center_utc_ns - start) / 1e9 for r in rows],
                    y_hz=[r.measured_cfo_hz for r in rows],
                    candidate_ids=[r.observation_id for r in rows],
                )
            )
        if not series:
            raise ValueError("no RF track meeting 14 observations / 7 seconds")
        archive = TleArchiveReader(Path("/var/lib/leo/tle"))
        snapshot = archive.select_latest_before(start - 505_000_000_000)
        name = snapshot.sha256 + ".tle"
        # Each process writes an identical immutable snapshot through its own temporary file.
        tmp = output / "evidence" / (sid + ".tle.tmp")
        tmp.write_text(archive.read(snapshot))
        tmp.replace(output / "evidence" / name)
        metadata = dict(
            session_id=sid,
            reference_utc_ns=start,
            tle_file=name,
            tle_digest=snapshot.digest,
            tle_collected_ns=snapshot.collected_utc_ns,
            sample_rate_hz=source.sample_rate_hz,
            partition="randomized",
            known_site_candidate_fields_used=False,
            capture_digest=source.input_manifest_sha256,
            analysis_digest=source.analysis_manifest_sha256,
        )
        write_json(
            output / "evidence" / f"{sid}.json",
            dict(
                inventory=metadata,
                series=series,
                episodes=[
                    dict(
                        episode_id=r["tracklet_id"],
                        members=[r["tracklet_id"]],
                        channel=r["channel"],
                    )
                    for r in series
                ],
            ),
        )
        return dict(
            session_id=sid,
            included=True,
            reference_utc_ns=start,
            episode_count=len(series),
            sample_rate_hz=source.sample_rate_hz,
        )
    except (ValueError, IndexError, FileNotFoundError, BundleNotFoundError) as exc:
        return dict(session_id=sid, included=False, reason=f"{type(exc).__name__}: {exc}")
    finally:
        sources.close()


def export(root, output, until_ns, workers):
    output.mkdir(parents=True, exist_ok=False)
    (output / "evidence").mkdir()
    captures = AdaptiveHopIqStore(root, read_only=True)
    try:
        ids = [
            sid
            for ts, sid in captures.publication_index()
            if until_ns - 48 * 3600 * 10**9 <= ts <= until_ns
        ]
    finally:
        captures.close()
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(export_one, [(sid, root, output) for sid in ids]):
            rows.append(row)
            if len(rows) % 10 == 0:
                print("exported", len(rows), "/", len(ids), flush=True)
    write_json(
        output / "inventory.json",
        dict(
            until_ns=until_ns,
            hours=48,
            scans=rows,
            selection_uses_tle_or_known_location=False,
            selection="longest-per-lane-from-RF-leading-hypothesis",
            partition="randomized",
        ),
    )


def run_part(args):
    run(args)
    return str(args.output)


def filter_span(evidence, output, minimum_span_s):
    output.mkdir(parents=True, exist_ok=False)
    (output / "evidence").mkdir()
    inventory = json.loads((evidence / "inventory.json").read_text())
    for row in inventory["scans"]:
        if not row["included"]:
            continue
        doc = json.loads((evidence / "evidence" / f"{row['session_id']}.json").read_text())
        doc["series"] = [s for s in doc["series"] if np.ptp(s["t_s"]) >= minimum_span_s]
        ids = {s["tracklet_id"] for s in doc["series"]}
        doc["episodes"] = [e for e in doc["episodes"] if e["episode_id"] in ids]
        row["episode_count"] = len(ids)
        row["included"] = bool(ids)
        if not ids:
            row["reason"] = "no RF track meets span sensitivity cut"
            continue
        name = doc["inventory"]["tle_file"]
        destination = output / "evidence" / name
        if not destination.exists():
            destination.symlink_to((evidence / "evidence" / name).resolve())
        write_json(output / "evidence" / f"{row['session_id']}.json", doc)
    inventory["minimum_span_s"] = minimum_span_s
    write_json(output / "inventory.json", inventory)


def search(
    evidence,
    output,
    spacing,
    points,
    workers,
    sigma_hz=250.0,
    minimum_elevation_deg=-1.0,
    max_per_partition=3,
    clock_s=0.0,
):
    """Parallel scan shards, merged by chronological scan order; same scorer and grid."""
    output.mkdir(parents=True, exist_ok=False)
    inv = json.loads((evidence / "inventory.json").read_text())
    rows = sorted([r for r in inv["scans"] if r["included"]], key=lambda r: r["reference_utc_ns"])
    tasks = []
    for k in range(min(workers, len(rows))):
        subset = output / f"input-{k}"
        subset.mkdir()
        (subset / "evidence").symlink_to((evidence / "evidence").resolve())
        write_json(
            subset / "inventory.json",
            dict(
                scans=rows[k::workers],
                prior_matched_norads_used=inv.get("prior_matched_norads_used", False),
            ),
        )
        tasks.append(
            SimpleNamespace(
                evidence=subset,
                output=output / f"part-{k}",
                center_lat=CENTER[0],
                center_lon=CENTER[1],
                region_size_km=WIDTH_KM,
                spacing_km=spacing,
                altitude_m=0.0,
                sigma_hz=sigma_hz,
                minimum_elevation_deg=minimum_elevation_deg,
                effective_count=6.0,
                clock_s=clock_s,
                max_per_partition=max_per_partition,
                scan_limit=None,
                shifted_grid=False,
                individual_sources=False,
                points=points,
            )
        )
    with ProcessPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run_part, tasks))
    first = tasks[0].output
    shutil.copy(first / "grid.npz", output / "grid.npz")
    g = Grid(**dict(np.load(output / "grid.npz")))
    total = np.zeros(len(g))
    evaluation = total.copy()
    history = []
    lookup = {}
    for task in tasks:
        for h in json.loads((task.output / "history.json").read_text()):
            lookup[h["session_id"]] = (h, task.output)
    for row in rows:
        h, part = lookup[row["session_id"]]
        path = part / f"{row['session_id']}.npz"
        shutil.copy(path, output / path.name)
        arrays = np.load(path)
        total += arrays["train_logbf"].sum(axis=0)
        evaluation += arrays["heldout_logbf"].sum(axis=0)
        h.update(summarize_grid(g, total, evaluation))
        history.append(h)
    np.savez_compressed(output / "accumulated.npz", train=total, heldout=evaluation)
    config = json.loads((first / "configuration.json").read_text())
    config.update(partition="randomized", inventory=str(evidence / "inventory.json"))
    write_json(output / "configuration.json", config)
    write_json(output / "history.json", history)
    write_json(
        output / "result.json",
        dict(
            config,
            **summarize_grid(g, total, evaluation),
            complete=True,
            scan_count=len(rows),
            episode_count=sum(r["episode_count"] for r in rows),
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["export", "search", "filter"])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--evidence", type=Path)
    p.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    p.add_argument("--until-ns", type=int)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--spacing-km", type=float, default=500.0)
    p.add_argument("--points", type=Path)
    p.add_argument("--minimum-span-s", type=float, default=30.0)
    p.add_argument("--sigma-hz", type=float, default=250.0)
    p.add_argument("--minimum-elevation-deg", type=float, default=-1.0)
    p.add_argument("--max-per-partition", type=int, default=3)
    p.add_argument("--clock-s", type=float, default=0.0)
    a = p.parse_args()
    if a.mode == "export":
        export(a.bulk_root, a.output, a.until_ns, a.workers)
    elif a.mode == "filter":
        filter_span(a.evidence, a.output, a.minimum_span_s)
    else:
        search(
            a.evidence,
            a.output,
            a.spacing_km,
            a.points,
            a.workers,
            a.sigma_hz,
            a.minimum_elevation_deg,
            a.max_per_partition,
            a.clock_s,
        )


if __name__ == "__main__":
    main()
