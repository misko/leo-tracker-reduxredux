"""Manifest-bound loading of fit-only compressed joint-orbit cache shards."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.research.compressed_orbit_states import CompressedOrbitRateStateGrid
from leo.analysis.research.orbit_rate_states import OrbitRateStateGrid
from leo.analysis.research.regional_doppler import REFERENCE_RF_HZ
from leo.analysis.research.shared_orbit_rate_fit import FixedPositionRateEpisode

MAXIMUM_DOPPLER_BOUND_HZ = 0.2
MAXIMUM_MINIMUM_RANGE_KM = 80.0


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_compressed_joint_cache(compressed_root: Path, source_root: Path):
    """Load one complete compressed session, verifying its raw-cache authority."""
    compressed_root, source_root = Path(compressed_root), Path(source_root)
    manifest_path = compressed_root / "manifest.json"
    source_manifest_path = source_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    source_manifest = json.loads(source_manifest_path.read_text())
    if (
        manifest.get("schema") != "compressed-orbit-rate-state-cache/v1"
        or manifest.get("complete") is not True
        or manifest.get("truth_accessed") is not False
        or manifest.get("fit_only") is not True
        or source_manifest.get("complete") is not True
        or source_manifest.get("truth_accessed") is not False
        or manifest.get("rf_hz") != REFERENCE_RF_HZ
        or not np.isfinite(manifest.get("minimum_range_km", np.nan))
        or not 0 < manifest["minimum_range_km"] <= MAXIMUM_MINIMUM_RANGE_KM
        or manifest.get("session_id") != source_manifest.get("session_id")
        or manifest.get("catalogue_size") != source_manifest.get("catalogue_size")
        or manifest.get("track_count") != len(source_manifest.get("tracks", ()))
        or manifest.get("provenance", {}).get("source_manifest") != _digest(source_manifest_path)
    ):
        raise ValueError("compressed cache does not bind a complete truth-free source cache")
    source_rows = {row["file"]: row for row in source_manifest["tracks"]}
    if len(source_rows) != len(source_manifest["tracks"]):
        raise ValueError("duplicate source shard")
    bounds = np.asarray(
        [
            row.get("conservative_off_node_doppler_bound_hz", np.nan)
            for row in manifest.get("tracks", ())
        ],
        dtype=float,
    )
    stated_maximum = manifest.get("maximum_conservative_off_node_doppler_bound_hz", np.nan)
    if (
        bounds.shape != (manifest["track_count"],)
        or not np.all(np.isfinite(bounds))
        or np.any(bounds < 0)
        or np.any(bounds > MAXIMUM_DOPPLER_BOUND_HZ)
        or not np.isfinite(stated_maximum)
        or stated_maximum < 0
        or stated_maximum > MAXIMUM_DOPPLER_BOUND_HZ
        or (len(bounds) and stated_maximum != float(np.max(bounds)))
    ):
        raise ValueError("compressed cache Doppler error bound is unqualified")
    episodes = []
    representations = []
    for row in manifest.get("tracks", ()):
        name = row.get("file")
        if not isinstance(name, str) or Path(name).name != name or name not in source_rows:
            raise ValueError("unsafe or unknown compressed shard")
        source_row = source_rows[name]
        shard = compressed_root / name
        source_shard = source_root / name
        if (
            row.get("episode_id") != source_row.get("episode_id")
            or row.get("source_digest") != source_row.get("digest")
            or row.get("source_digest") != _digest(source_shard)
            or row.get("compressed_digest") != _digest(shard)
        ):
            raise ValueError("compressed shard provenance differs")
        with np.load(shard, allow_pickle=False) as arrays:
            common = {"rate_nodes_s_h", "candidate_norad", "observed_hz", "segment", "training"}
            if not common.issubset(arrays.files):
                raise ValueError("compressed shard lacks episode arrays")
            representation = row.get("representation")
            if representation == "chebyshev-time-coefficients":
                required = {
                    "time_s",
                    "time_interval_s",
                    "position_coefficients_km",
                    "velocity_coefficients_km_s",
                }
                if not required.issubset(arrays.files):
                    raise ValueError("compressed shard lacks coefficient arrays")
                grid = CompressedOrbitRateStateGrid(
                    arrays["rate_nodes_s_h"],
                    arrays["time_s"],
                    arrays["time_interval_s"],
                    arrays["position_coefficients_km"],
                    arrays["velocity_coefficients_km_s"],
                )
            elif representation in ("raw-fallback-no-state-saving", "raw-fallback-no-file-saving"):
                required = {"position_nodes_km", "velocity_nodes_km_s"}
                if not required.issubset(arrays.files):
                    raise ValueError("raw fallback lacks state arrays")
                grid = OrbitRateStateGrid(
                    arrays["rate_nodes_s_h"],
                    arrays["position_nodes_km"],
                    arrays["velocity_nodes_km_s"],
                )
            else:
                raise ValueError("unknown compressed representation")
            candidate = np.asarray(arrays["candidate_norad"])
            if len(candidate) != row.get("candidate_count"):
                raise ValueError("compressed candidate accounting differs")
            episodes.append(
                FixedPositionRateEpisode(
                    manifest["session_id"] + "/" + row["episode_id"],
                    np.asarray(arrays["observed_hz"]),
                    candidate,
                    np.asarray(arrays["segment"]),
                    np.asarray(arrays["training"]),
                    grid,
                    manifest["catalogue_size"],
                )
            )
            representations.append(representation)
    if len(episodes) != manifest["track_count"] or set(source_rows) != {
        row["file"] for row in manifest["tracks"]
    }:
        raise ValueError("compressed cache has incomplete track coverage")
    provenance = {
        "compressed_manifest": _digest(manifest_path),
        "source_manifest": _digest(source_manifest_path),
        "representations": tuple(representations),
    }
    return episodes, provenance
