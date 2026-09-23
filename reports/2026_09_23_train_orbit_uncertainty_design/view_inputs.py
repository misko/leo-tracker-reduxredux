"""Reconstruct the four sealed, training-only first-six tau-zero arms."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json"
SINGLE = ROOT / "reports/2026_09_23_long_training_search/search.py"
LOADER = ROOT / "reports/2026_09_23_long_training_fast_score/loader.py"
FIRST = ROOT / "reports/2026_09_23_long_training_search_multi/results/inference.json"
SECOND = ROOT / "reports/2026_09_23_long_second8h_training_baseline/results/inference.json"
FIRST_SOURCE = ROOT / "reports/2026_09_23_long_training_search_multi/search.py"
SECOND_SOURCE = ROOT / "reports/2026_09_23_long_second8h_training_baseline/search.py"
SECOND_MANIFEST = ROOT / "reports/2026_09_23_long_training_cache_second8h/manifest.json"
FIRST_CACHE = Path("/tmp/leo-long-training-cache-first16")
SECOND_CACHE = Path("/tmp/leo-long-training-cache-second8h")
RADIUS_KM = 6371.0088


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def inverse_offset(origin: tuple[float, float], point: tuple[float, float]) -> tuple[float, float]:
    """Return the east/north coordinates used by ``single.offset_coordinate``."""
    latitude, longitude, target_latitude, target_longitude = np.deg2rad(
        [origin[0], origin[1], point[0], point[1]]
    )
    delta_longitude = target_longitude - longitude
    cosine = np.sin(latitude) * np.sin(target_latitude) + np.cos(latitude) * np.cos(
        target_latitude
    ) * np.cos(delta_longitude)
    distance = RADIUS_KM * np.arccos(np.clip(cosine, -1.0, 1.0))
    bearing = np.arctan2(
        np.sin(delta_longitude) * np.cos(target_latitude),
        np.cos(latitude) * np.sin(target_latitude)
        - np.sin(latitude) * np.cos(target_latitude) * np.cos(delta_longitude),
    )
    return float(distance * np.sin(bearing)), float(distance * np.cos(bearing))


def _read_sealed(path: Path) -> dict[str, Any]:
    expected = path.with_suffix(".sha256").read_text().strip()
    actual = digest(path).removeprefix("sha256:")
    if actual != expected:
        raise ValueError(f"sealed baseline digest differs: {path}")
    return json.loads(path.read_text())


def _cache_bindings(
    baseline: dict[str, Any], session_ids: list[str], cache_root: Path
) -> list[dict[str, str]]:
    expected = {row["session_id"]: row for row in baseline["bindings"]["sessions"]}
    if not set(session_ids).issubset(expected):
        raise ValueError("baseline lacks a required first-six cache binding")
    rows = []
    for session_id in session_ids:
        receipt = cache_root / session_id / "cache_receipt.json"
        cache = cache_root / session_id / "state_cache.npz"
        binding = expected[session_id]
        if digest(receipt) != binding["receipt"] or digest(cache) != binding["cache"]:
            raise ValueError(f"cache binding differs: {session_id}")
        rows.append(
            {
                "session_id": session_id,
                "receipt": binding["receipt"],
                "cache": binding["cache"],
            }
        )
    return rows


def _arm(
    *,
    group: str,
    prior_name: str,
    session_ids: list[str],
    selected: dict[str, Any],
    baseline: dict[str, Any],
    baseline_path: Path,
    baseline_source: Path,
    cache_root: Path,
    single: Any,
    loader: Any,
) -> dict[str, Any]:
    point = (float(selected["latitude_deg"]), float(selected["longitude_deg"]))
    prior = single.PRIORS[prior_name]
    initial_xy = inverse_offset((float(prior[0]), float(prior[1])), point)
    reconstructed = single.offset_coordinate(prior[:2], *initial_xy)
    if single.haversine_km(point, reconstructed) > 1e-7:
        raise ValueError("baseline coordinate inverse does not round-trip")
    if np.hypot(*initial_xy) >= float(prior[2]):
        raise ValueError("baseline seed lies outside the declared prior disk")
    cache_rows = _cache_bindings(baseline, session_ids, cache_root)
    scans = []
    for session_id in session_ids:
        loaded = loader.load_session(single, cache_root / session_id, session_id)
        _, tracks = single.score_point(loaded["prepared"], loaded["candidate_ids"], *point, False)
        if len(tracks) != len(loaded["prepared"]):
            raise ValueError(f"fixed-track reconstruction differs: {session_id}")
        if any(row["candidate_id"] is None for row in tracks):
            raise ValueError(f"no finite training-only candidate: {session_id}")
        scans.append(
            {
                "session_id": session_id,
                "tracks": [
                    {"track_id": row["track_id"], "candidate_id": row["candidate_id"]}
                    for row in tracks
                ],
            }
        )
    return {
        "group": group,
        "prior": prior_name,
        "session_ids": session_ids,
        "cache_root": str(cache_root),
        "selected": {"latitude_deg": point[0], "longitude_deg": point[1]},
        "initial_xy_km": {"east": initial_xy[0], "north": initial_xy[1]},
        "scans": scans,
        "bindings": {
            "manifest": digest(MANIFEST),
            "second_baseline_manifest": digest(SECOND_MANIFEST),
            "baseline": digest(baseline_path),
            "baseline_source": digest(baseline_source),
            "single_tool": digest(SINGLE),
            "loader": digest(LOADER),
            "cache_rows": cache_rows,
        },
    }


def load_view_arms() -> list[dict[str, Any]]:
    """Return the four frozen first-six arms without reading held outcomes."""
    manifest = json.loads(MANIFEST.read_text())["partitions"]
    first_ids = manifest["train"]["session_ids"][:6]
    second_ids = manifest["train"]["session_ids"][72:78]
    if len(first_ids) != 6 or len(second_ids) != 6 or set(first_ids) & set(second_ids):
        raise ValueError("expected two disjoint six-session TRAIN prefixes")
    if set(first_ids + second_ids) & set(manifest["validation"]["session_ids"]):
        raise ValueError("view overlaps validation")
    if set(first_ids + second_ids) & set(manifest["test"]["session_ids"]):
        raise ValueError("view overlaps test")
    first, second = _read_sealed(FIRST), _read_sealed(SECOND)
    if digest(MANIFEST) != first["bindings"]["manifest"]:
        raise ValueError("first baseline manifest binding differs")
    if digest(SECOND_MANIFEST) != second["bindings"]["manifest"]:
        raise ValueError("second baseline manifest binding differs")
    if digest(SINGLE) != first["bindings"]["single_tool"]:
        raise ValueError("first baseline single-tool binding differs")
    if digest(SINGLE) != second["bindings"]["single_tool"]:
        raise ValueError("second baseline single-tool binding differs")
    if digest(LOADER) != second["bindings"]["fast_loader"]:
        raise ValueError("second baseline fast-loader binding differs")
    if digest(FIRST_SOURCE) != first["bindings"]["tool"]:
        raise ValueError("first baseline source binding differs")
    if digest(SECOND_SOURCE) != second["bindings"]["tool"]:
        raise ValueError("second baseline source binding differs")
    first_view = next(view for view in first["views"] if view["scan_count"] == 6)
    if first_view["session_ids"] != first_ids:
        raise ValueError("first baseline first-six IDs differ")
    if second["session_ids"][:6] != second_ids:
        raise ValueError("second baseline first-six IDs differ")
    single = load_module(SINGLE, "view_inputs_single")
    loader = load_module(LOADER, "view_inputs_loader")
    arms = []
    for prior_name in ("sacramento", "reno"):
        first_search = next(row for row in first_view["searches"] if row["prior"] == prior_name)
        second_arm = next(
            row for row in second["arms"] if row["scan_count"] == 6 and row["prior"] == prior_name
        )
        arms.append(
            _arm(
                group="first6",
                prior_name=prior_name,
                session_ids=first_ids,
                selected=first_search["selected"],
                baseline=first,
                baseline_path=FIRST,
                baseline_source=FIRST_SOURCE,
                cache_root=FIRST_CACHE,
                single=single,
                loader=loader,
            )
        )
        arms.append(
            _arm(
                group="second6",
                prior_name=prior_name,
                session_ids=second_ids,
                selected=second_arm["search"]["selected"],
                baseline=second,
                baseline_path=SECOND,
                baseline_source=SECOND_SOURCE,
                cache_root=SECOND_CACHE,
                single=single,
                loader=loader,
            )
        )
    return arms
