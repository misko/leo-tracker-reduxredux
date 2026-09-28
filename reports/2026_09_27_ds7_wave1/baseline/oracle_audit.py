#!/usr/bin/env python3
"""Load the pinned DS6 numerical oracle without importing historical reports at runtime.

The audit extracts only ``Stationary`` from the pinned run_full source and executes
the standalone pinned fast offset solver. It compares those equations with the DS7
port on the already-frozen first-session banks. It never opens DS7 pose or scores.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[3]
COMMIT = "75b76f66974c78588c6599822e8007aaa767466b"
SESSION = "scan-fw-5f7bf896e4552887"


def source(path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{COMMIT}:{path}"], cwd=ROOT, text=True
    )


def main() -> None:
    fast_namespace: dict = {}
    exec(
        compile(
            source("reports/2026_09_27_ds6_full_stationary/fast_solver.py"),
            "pinned-fast_solver.py",
            "exec",
        ),
        fast_namespace,
    )
    tree = ast.parse(source("reports/2026_09_27_ds6_full_stationary/run_full.py"))
    stationary = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Stationary"
    )
    spec = importlib.util.spec_from_file_location("baseline_port", ROOT / "tools/ds7_baseline_adapter.py")
    port = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(port)
    oracle_namespace = {
        "np": np,
        "profile": fast_namespace["profile"],
        "site": port.site,
        "REFERENCE_RF_HZ": port.REFERENCE_RF_HZ,
        "LIGHT_KM_S": port.LIGHT_KM_S,
        "logsumexp": logsumexp,
    }
    exec(
        compile(ast.Module(body=[stationary], type_ignores=[]), "pinned-Stationary.py", "exec"),
        oracle_namespace,
    )
    tracks = json.loads(
        (ROOT / f"reports/2026_09_27_ds7_wave1/baseline/exports/{SESSION}-tracks.json").read_text()
    )
    bank_root = ROOT / f".leo/ds7-wave1/baseline/{SESSION}"
    manifest = json.loads((bank_root / "manifest.json").read_text())
    banks_file = np.load(bank_root / "banks.npz")
    config = json.loads((ROOT / "config/ds7/baseline-ready-v1.json").read_text())["config"]
    port_tracks, oracle_tracks, banks = [], [], {}
    for item in manifest["tracks"][:6]:
        index = item["index"]
        row = tracks["tracks"][index]
        position = banks_file[f"position_km_{index}"]
        velocity = banks_file[f"velocity_km_s_{index}"]
        mask = np.asarray(row["training_mask"], bool)
        measured = np.asarray(row["measured_hz"])
        port_tracks.append(
            dict(
                row,
                candidate_position_km=position,
                candidate_velocity_km_s=velocity,
                catalogue_size=manifest["catalogue_size"],
                y=measured,
                mask=mask,
            )
        )
        oracle_tracks.append(dict(row, t=np.asarray(row["times_s"]), y=measured, mask=mask))
        banks[row["track_id"]] = (position, velocity, None)

    class Base:
        tracks = oracle_tracks
        catalogue_size = manifest["catalogue_size"]

        def __init__(self):
            self.banks = banks

        def coordinates(self, point):
            center = config["geographic_prior_center_deg"]
            return (
                center[0] + point[1] / 111.195,
                center[1] + point[0] / (111.195 * np.cos(np.radians(center[0]))),
            )

    oracle = oracle_namespace["Stationary"](Base())
    candidate = port.Stationary({"tracks": port_tracks}, config)
    points = (
        np.array([0.0, 0.0, 0.0]),
        np.array([3.705984977262451, -1.9755568160870454, -0.2772259707590678]),
    )
    comparisons = []
    for point in points:
        expected = oracle.evaluate(point, True)
        actual = candidate.evaluate(point, True)
        comparisons.append(
            {
                "point": point.tolist(),
                "train_abs_difference": abs(expected["train"] - actual[0]),
                "gradient_max_abs_difference": float(
                    np.max(np.abs(expected["gradient"] - actual[1]))
                ),
            }
        )
    print(json.dumps({"commit": COMMIT, "tracks_compared": 6, "points": comparisons}, indent=2))


if __name__ == "__main__":
    main()
