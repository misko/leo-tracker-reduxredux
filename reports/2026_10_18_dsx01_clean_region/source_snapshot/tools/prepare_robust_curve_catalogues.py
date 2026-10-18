"""Freeze a response-only polynomial repair before matched satellite searches."""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from associate_merged_track_catalogue import load_tracks, write
from localize_merged_track_catalogue import raw_curvature

from leo.analysis.research.robust_polynomial_order import partition_catalogue

ROOT = Path(__file__).resolve().parents[1]


def run(case, output):
    recording = (
        ROOT
        / "reports/2026_10_17_ds22_merged_satellites"
        / ("dsx01_adapter" if case.startswith("DSX") else "cohort")
        / case
    )
    tracks = load_tracks(recording)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    cores, background, reviews = partition_catalogue(tracks)
    write(output / "curves.json", cores)
    write(output / "background.json", background)
    write(output / "reviews.json", reviews)
    originals = {oid for track in tracks for oid in track["observation_ids"]}
    retained = {oid for track in cores for oid in track["observation_ids"]}
    discarded_from_curves = {row["observation_id"] for row in background}
    assert retained.isdisjoint(discarded_from_curves)
    assert originals == retained | discarded_from_curves
    receipt = dict(
        case=case,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        robust_source_sha256=hashlib.sha256(
            (ROOT / "src/leo/analysis/research/robust_polynomial_order.py").read_bytes()
        ).hexdigest(),
        original_tracks_sha256=hashlib.sha256((recording / "tracks.json").read_bytes()).hexdigest(),
        curves_sha256=hashlib.sha256((output / "curves.json").read_bytes()).hexdigest(),
        background_sha256=hashlib.sha256((output / "background.json").read_bytes()).hexdigest(),
        original_fragments=len(tracks),
        core_fragments=len(cores),
        original_points=len(originals),
        curve_points=len(retained),
        background_points=len(background),
        original_curved_fragments=sum(raw_curvature(t) for t in tracks),
        core_curved_fragments=sum(raw_curvature(t) for t in cores),
        tracks_with_background=sum(r["background_points"] > 0 for r in reviews),
        core_degree_counts=dict(Counter(p["degree"] for t in cores for p in t["pieces"])),
        original_degree_counts=dict(Counter(p["degree"] for t in tracks for p in t["pieces"])),
        maximum_degree=4,
        noise_hz=150.0,
        clutter_probability=0.02,
        clutter_width_hz=1 / 4.4e-6,
        penalty="(degree+1)*log(original point count)",
        input_alias_branches_frozen=True,
        input_values_and_times_unchanged=True,
        every_original_point_scored=True,
        points_dropped=0,
        reference_position_used=False,
        satellite_identity_or_tle_used=False,
        elapsed_seconds=time.monotonic() - started,
    )
    write(output / "receipt.json", receipt)
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", choices=("DS22-001", "DSX01-S01"), required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if Path("/mnt/qnap01") in (a.output.resolve(), *a.output.resolve().parents):
        p.error("QNAP is read-only")
    run(a.case, a.output)
