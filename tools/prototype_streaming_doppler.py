"""Export recorded Doppler evidence to a private, bounded native experiment.

Published track memberships are inputs to this replay, not an independent
detector qualification. Satellite winners and the known site never enter the
native input. All storage locations are explicit arguments or archive ports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def spline_nodes(track: dict, count: int = 13) -> tuple[np.ndarray, np.ndarray, dict]:
    """Fit a small C2 cubic regression spline on training observations only."""
    t = np.asarray(track["times_s"], dtype=float)
    y = np.asarray(track["measured_hz"], dtype=float)
    train = np.asarray(track["training_mask"], dtype=bool)
    if (
        t.ndim != 1
        or len(t) < 6
        or y.shape != t.shape
        or train.shape != t.shape
        or not np.isfinite(t).all()
        or not np.isfinite(y).all()
        or np.any(np.diff(t) <= 0)
        or train.sum() < 4
        or train.all()
    ):
        raise ValueError("invalid independently partitioned track")
    duration = t[-1] - t[0]
    u = (t - t[0]) / duration
    # Sparse tracks use a cubic; denser tracks add up to three interior knots.
    interiors = np.linspace(0, 1, min(3, max(0, int(train.sum()) // 16 - 1)) + 2)[1:-1]

    def design(x):
        return np.column_stack(
            [np.ones_like(x), x, x * x, x * x * x, *[np.maximum(x - k, 0) ** 3 for k in interiors]]
        )

    baseline = float(np.mean(y[train]))
    coef, _, rank, _ = np.linalg.lstsq(design(u[train]), y[train] - baseline, rcond=None)
    if rank != len(coef):
        raise ValueError("rank deficient training spline")
    query = np.linspace(0, 1, count)
    values = design(query) @ coef + baseline
    residual = y - (design(u) @ coef + baseline)
    return (
        t[0] + query * duration,
        values,
        {
            "interior_knots_normalized": interiors.tolist(),
            "training_rms_hz": float(np.sqrt(np.mean(residual[train] ** 2))),
            "validation_rms_hz": float(np.sqrt(np.mean(residual[~train] ** 2))),
            "training_count": int(train.sum()),
            "validation_count": int((~train).sum()),
        },
    )


def prepare(
    position: dict, capture: dict, tle_text: str, region_name: str
) -> tuple[str, str, dict]:
    capture = capture.get("manifest", capture)
    if position["session_id"] != capture["session_id"] or position[
        "input_manifest_sha256"
    ] != canonical_digest(capture):
        raise ValueError("capture binding mismatch")
    digest = "sha256:" + hashlib.sha256(tle_text.encode("ascii")).hexdigest()
    if digest != position["diagnostics"]["snapshot_digest"]:
        raise ValueError("TLE snapshot binding mismatch")
    region = next(p["region"] for p in position["priors"] if p["name"] == region_name)
    if region["altitude_m"] != 0 or not 0 < region["radius_km"] <= 500:
        raise ValueError("prototype requires a ground region of at most 500 km")
    tracks = position["diagnostics"]["track_evidence"]
    catalog = parse_element_sets(tle_text)
    ids = {
        number
        for name, number in zip(catalog.names, catalog.satellite_numbers, strict=True)
        if name.upper().startswith("STARLINK") and "DEB" not in name.upper()
    }
    # Preserve exact TLE bytes; selection depends only on catalogue labels.
    from leo.native_pipeline.orbit_input import catalogue_id

    lines = tle_text.splitlines()
    pairs = [
        (line, lines[i + 1])
        for i, line in enumerate(lines)
        if line.startswith("1 ") and catalogue_id(line[2:7]) in ids
    ]
    tle_input = str(len(pairs)) + "\n" + "\n".join(v for pair in pairs for v in pair) + "\n"
    origin = capture["timing"]["first_sample_estimate_utc_ns"]
    # Match the published replay's nominal RF convention, not its selected identities.
    rows = [
        f"SDP1 {origin} 11200000000 {region['center_latitude_deg']:.17g} "
        f"{region['center_longitude_deg']:.17g} {region['radius_km']:.17g} 60 5 30 20 8",
        str(len(tracks)),
    ]
    metadata = []
    for track in tracks:
        nodes, values, fit = spline_nodes(track)
        rows.append(f"{len(track['times_s'])} {len(nodes)}")
        rows.extend(
            f"{t:.17g} {y:.17g} {int(m)}"
            for t, y, m in zip(
                track["times_s"], track["measured_hz"], track["training_mask"], strict=True
            )
        )
        rows.extend(f"{t:.17g} {y:.17g}" for t, y in zip(nodes, values, strict=True))
        metadata.append(
            {
                "track_id": track["track_id"],
                "support_digest": track["support_digest"],
                "start_s": nodes[0],
                "end_s": nodes[-1],
                "spline": fit,
            }
        )
    return (
        "\n".join(rows) + "\n",
        tle_input,
        {
            "schema": "leo-streaming-doppler-experiment/v1",
            "session_id": capture["session_id"],
            "capture_digest": position["input_manifest_sha256"],
            "tle_digest": digest,
            "origin_utc_ns": origin,
            "region_name": region_name,
            "region": region,
            "catalogue_records": len(pairs),
            "tracks": metadata,
            "time_offset_bound_s": 60,
            "carrier_hz": 11200000000,
            "track_memberships": "published measured evidence; not independent reconstruction",
            "known_position_used_for_inference": False,
            "published_identities_used": False,
            "position_fix_claimed": False,
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--position-document", required=True, type=Path)
    p.add_argument("--capture-manifest", required=True, type=Path)
    p.add_argument("--tle-root", required=True, type=Path)
    p.add_argument("--region", default="sacramento")
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    position = json.loads(a.position_document.read_text())
    capture = json.loads(a.capture_manifest.read_text())
    reader = TleArchiveReader(a.tle_root)
    snapshot = next(
        s for s in reader.list_snapshots() if s.digest == position["diagnostics"]["snapshot_digest"]
    )
    data, tles, meta = prepare(position, capture, reader.read(snapshot), a.region)
    a.output.mkdir(parents=True, exist_ok=False)
    for name, content in (("observations.txt", data), ("catalogue.tle", tles)):
        (a.output / name).write_text(content)
    meta["input_hashes"] = {
        name: hashlib.sha256((a.output / name).read_bytes()).hexdigest()
        for name in ("observations.txt", "catalogue.tle")
    }
    (a.output / "input.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(
        json.dumps(
            {
                "tracks": len(meta["tracks"]),
                "catalogue_records": meta["catalogue_records"],
                "output": str(a.output),
            }
        )
    )


if __name__ == "__main__":
    main()
