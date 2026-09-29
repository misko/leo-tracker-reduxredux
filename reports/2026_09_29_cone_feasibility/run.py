"""Evaluate conservative exclusions and replay the published point audit."""

import json
import sys
from pathlib import Path

import numpy as np
from bounds import candidate_lower_bounds, geographic_envelope

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_09_29_rx_cone_consistency"
sys.path.insert(0, str(PRIOR))
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from cones import axes, enu_los  # noqa: E402
from ds7_baseline_adapter import site  # noqa: E402


def read(path):
    return json.loads(path.read_text())


def main(key):
    plan = read(HERE / "plan.json")
    config = plan["config"]
    assert config["position_bounds_km"] == [-12, 12]
    assert config["timing_bounds_s"] == [-5, 5] and config["altitude_km"] == 0
    grid = np.asarray(config["timing_grid_s"])
    assert grid[0] == -5 and grid[-1] == 5 and np.all(np.diff(grid) > 0)
    unit = next(u for u in plan["units"] if u["unit_id"] == key)
    docs = baseline.load_documents({"config": config, "inputs": unit["group"]["inputs"]})
    old = read(PRIOR / "runs" / key / "result.json")
    old_rows = {(r["session_id"], r["track_id"]): r for r in old["rows"]}
    assert len(old_rows) == len(old["rows"]) == unit["group"]["tracks"]
    assert old["position_and_timings"] == unit["x"]
    assert np.max(np.abs(unit["x"][:2])) <= 12 and np.max(np.abs(unit["x"][2:])) <= 5
    lat, lon = config["geographic_prior_center_deg"]
    receiver, _ = site(lat, lon)
    latitude, longitude = np.radians([lat, lon])
    frame = np.array(
        [
            [-np.sin(longitude), np.cos(longitude), 0],
            [
                -np.sin(latitude) * np.cos(longitude),
                -np.sin(latitude) * np.sin(longitude),
                np.cos(latitude),
            ],
            [
                np.cos(latitude) * np.cos(longitude),
                np.cos(latitude) * np.sin(longitude),
                np.sin(latitude),
            ],
        ]
    )
    envelope = geographic_envelope(lat)
    old_lat, old_lon = baseline.Stationary(docs[0], config).coordinates(unit["x"])
    old_receiver, _ = site(old_lat, old_lon)
    rows = []
    for doc, timing in zip(docs, unit["x"][2:], strict=True):
        for track in doc["tracks"]:
            identity = doc["session_id"], track["track_id"]
            prior = old_rows[identity]
            rx, mask = int(track["receiver_id"]), track["mask"]
            assert rx in (0, 1) and rx == prior["receiver"]
            assert int(mask.sum()) == prior["training_observations"]
            assert int((~mask).sum()) == prior["held_observations"]
            p = track["candidate_position_km"]
            assert p.shape[0] == prior["candidates"] and p.shape[1] == len(grid)
            lower = candidate_lower_bounds(
                p, mask, receiver, axes("nominal")[rx] @ frame, **envelope
            )
            los = enu_los(p, grid, timing, old_receiver, old_lat, old_lon)
            angles = np.degrees(np.arccos(np.clip(los @ axes("nominal")[rx], -1, 1)))
            worst = angles[:, mask].max(axis=1)
            point = prior["controls"]["nominal"]
            assert abs(float(worst.min()) - point["minimum_training_half_angle_deg"]) < 1e-8
            assert np.all(lower <= worst + 1e-7)
            widths = []
            for width, old_width in zip(plan["half_angles_deg"], point["widths"], strict=True):
                assert width == old_width["half_angle_deg"]
                supported = int(np.sum(worst <= width))
                assert supported == old_width["supported_candidates"]
                excluded = lower > width + 1e-7
                assert not np.any(excluded & (worst <= width))
                widths.append(
                    {
                        "half_angle_deg": width,
                        "excluded_candidates": int(excluded.sum()),
                        "track_excluded": bool(excluded.all()),
                        "point_supported_candidates": supported,
                    }
                )
            rows.append(
                {
                    "session_id": identity[0],
                    "track_id": identity[1],
                    "receiver": rx,
                    "candidates": len(lower),
                    "training_observations": int(mask.sum()),
                    "held_observations": int((~mask).sum()),
                    "candidate_lower_bounds_deg": lower.tolist(),
                    "point_candidate_worst_angles_deg": worst.tolist(),
                    "widths": widths,
                }
            )
    assert {(r["session_id"], r["track_id"]) for r in rows} == old_rows.keys()
    assert sum(r["training_observations"] for r in rows) == unit["group"]["training_observations"]
    assert sum(r["held_observations"] for r in rows) == unit["group"]["held_observations"]
    with (HERE / "runs" / key / "result.json").open("x") as f:
        json.dump(
            {"unit_id": key, "envelope": envelope, "point_replay_passed": True, "rows": rows},
            f,
            indent=2,
            allow_nan=False,
        )
    print(key, "validated", len(rows), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
