"""Local profiled position curvature with scan or satellite epoch nuisances."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def profile_information(position_information, groups, ridge):
    profiled = position_information.copy()
    for value in groups.values():
        if value["epoch_curvature"] + ridge > 0:
            cross = value["cross"]
            profiled -= np.outer(cross, cross) / (value["epoch_curvature"] + ridge)
    values, vectors = np.linalg.eigh(position_information)
    if np.min(values) <= 0:
        raise ValueError("baseline position curvature singular")
    inverse_root = (vectors / np.sqrt(values)) @ vectors.T
    fractions = np.linalg.eigvalsh(inverse_root @ profiled @ inverse_root)
    return {
        "profiled_position_matrix": profiled.tolist(),
        "trace_fraction_retained": float(np.trace(profiled) / np.trace(position_information)),
        "directional_fractions_retained": fractions.tolist(),
    }


def predict(single, position, velocity, point):
    receiver, _ = single.receiver_ecef(*point)
    delta = position - receiver
    return (
        -single.REFERENCE_RF_HZ
        / single.LIGHT_KM_S
        * np.sum(delta * velocity, axis=1)
        / np.linalg.norm(delta, axis=1)
    )


def main():
    single_path = HERE.parent / "2026_09_23_long_training_search/search.py"
    epoch_path = HERE.parent / "2026_09_23_long_shared_epoch_position/fit.py"
    baseline_path = HERE.parent / "2026_09_23_long_training_search_multi/results/results.json"
    manifest_path = HERE.parent / "2026_09_23_long_inventory_complete/manifest.json"
    single = load("epoch_info_single", single_path)
    epoch = load("epoch_info_fit", epoch_path)
    baseline_document = json.loads(baseline_path.read_text())
    baseline = baseline_document["views"][0]
    ids = json.loads(manifest_path.read_text())["partitions"]["train"]["session_ids"][:6]
    assert ids == baseline["session_ids"]
    cache_root = Path("/tmp/leo-long-training-cache-first16")
    cache_bindings = {r["session_id"]: r for r in baseline_document["bindings"]["sessions"]}
    for sid in ids:
        for name, filename in (("receipt", "cache_receipt.json"), ("cache", "state_cache.npz")):
            if digest(cache_root / sid / filename) != cache_bindings[sid][name]:
                raise ValueError(f"frozen cache binding differs for {sid}: {name}")
    rows = []
    for arm in baseline["searches"]:
        point = (arm["selected"]["latitude_deg"], arm["selected"]["longitude_deg"])
        scans = [
            epoch.prepare_scan(single, cache_root / sid, scan)
            for sid, scan in zip(ids, arm["selected"]["scans"], strict=True)
        ]
        for tau_step in (0.05, 0.01):
            info = np.zeros((2, 2))
            groups = {"scan": {}, "satellite": {}}
            active = capped = 0
            for scan in scans:
                for track in scan["tracks"]:
                    mask = track["training_mask"]
                    pos, vel = epoch.interpolate_selected(track, 0.0)
                    measured = track["measured_hz"][mask]
                    residual = measured - predict(single, pos, vel, point)[mask]
                    residual -= np.mean(residual)
                    if np.sqrt(np.mean(residual**2)) >= 800:
                        capped += 1
                        continue
                    active += 1
                    derivatives = []
                    for east, north in ((0.1, 0.0), (0.0, 0.1)):
                        plus = single.offset_coordinate(point, east, north)
                        minus = single.offset_coordinate(point, -east, -north)
                        d = (predict(single, pos, vel, plus) - predict(single, pos, vel, minus))[
                            mask
                        ] / 0.2
                        derivatives.append(d - np.mean(d))
                    a = np.column_stack(derivatives)
                    plus = epoch.interpolate_selected(track, tau_step)
                    minus = epoch.interpolate_selected(track, -tau_step)
                    b = (predict(single, *plus, point) - predict(single, *minus, point))[mask] / (
                        2 * tau_step
                    )
                    b -= np.mean(b)
                    weight = track["weight_s"] / len(measured)
                    info += weight * (a.T @ a)
                    for family, key in (
                        ("scan", scan["session_id"]),
                        ("satellite", track["candidate_id"]),
                    ):
                        value = groups[family].setdefault(
                            key, {"cross": np.zeros(2), "epoch_curvature": 0.0}
                        )
                        value["cross"] += weight * (a.T @ b)
                        value["epoch_curvature"] += weight * float(b @ b)
            scenarios = []
            for family, family_groups in groups.items():
                for scale in (0.2, 1.0, 5.0, None):
                    ridge = 0.0 if scale is None else 800.0**2 / scale**2
                    scenarios.append(
                        {
                            "family": family,
                            "scale_s": scale,
                            "nuisance_count": len(family_groups),
                            **profile_information(info, family_groups, ridge),
                        }
                    )
            rows.append(
                {
                    "prior": arm["prior"],
                    "tau_difference_step_s": tau_step,
                    "position_difference_step_km": 0.1,
                    "active_tracks": active,
                    "capped_tracks": capped,
                    "baseline_position_matrix": info.tolist(),
                    "scenarios": scenarios,
                }
            )
    result = {
        "session_ids": ids,
        "rows": rows,
        "interpretation": (
            "local Gauss-Newton curvature of capped duration objective, "
            "not calibrated Fisher information or a CRLB; fixed identities, cap set and visibility"
        ),
        "bindings": {
            str(p): digest(p)
            for p in (Path(__file__), single_path, epoch_path, baseline_path, manifest_path)
        },
    }
    (HERE / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        if row["tau_difference_step_s"] == 0.05:
            print(
                row["prior"],
                [
                    (s["family"], s["scale_s"], s["directional_fractions_retained"])
                    for s in row["scenarios"]
                ],
            )


if __name__ == "__main__":
    main()
