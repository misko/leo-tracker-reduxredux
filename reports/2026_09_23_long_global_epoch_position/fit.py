#!/usr/bin/env python3
"""Fit position and one conditional global epoch effect on nested 00Z TRAIN views."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize, minimize_scalar

SCALES = (0.2, 1.0, 5.0)


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prepare(single, cache_root, session_ids, baseline_scans):
    tracks = []
    bindings = []
    for session_id, baseline_scan in zip(session_ids, baseline_scans, strict=True):
        directory = cache_root / session_id
        receipt_path, cache_path = directory / "cache_receipt.json", directory / "state_cache.npz"
        receipt = json.loads(receipt_path.read_text())
        if receipt["session_id"] != session_id or baseline_scan["session_id"] != session_id:
            raise ValueError("cache/baseline scan order differs from frozen cohort")
        archive = np.load(cache_path, allow_pickle=False)
        arrays = {key: archive[key] for key in archive.files}
        candidate_index = {str(value): index for index, value in enumerate(arrays["candidate_id"])}
        evidence = {row["track_id"]: row for row in receipt["prepared_evidence"]["tracks"]}
        for selected in baseline_scan["tracks"]:
            source = evidence[selected["track_id"]]
            index = candidate_index[selected["candidate_id"]]
            times = np.asarray(source["times_s"], dtype=float)
            tracks.append(
                {
                    "session_id": session_id,
                    "track_id": source["track_id"],
                    "candidate_id": selected["candidate_id"],
                    "times_s": times,
                    "measured_hz": np.asarray(source["measured_hz"], dtype=float),
                    "training_mask": np.asarray(source["training_mask"], dtype=bool),
                    "weight_s": int(len(np.unique(np.floor(times)))),
                    "grid_ns": arrays["receive_plus_tau_offset_ns"],
                    "position": arrays["position_ecef_km"][index],
                    "velocity": arrays["velocity_ecef_km_s"][index],
                }
            )
        bindings.append(
            {"session_id": session_id, "receipt": digest(receipt_path), "cache": digest(cache_path)}
        )
    return tracks, bindings


def interpolate(track, eta):
    grid = track["grid_ns"]
    query = np.rint((track["times_s"] + eta) * 1e9).astype(np.int64)
    if np.any(query < grid[0]) or np.any(query > grid[-1]):
        raise ValueError("epoch query outside cache")
    fraction = (query - grid[0]) / float(grid[1] - grid[0])
    low = np.floor(fraction).astype(int)
    high = np.minimum(low + 1, len(grid) - 1)
    weight = fraction - low
    position = track["position"][low] * (1 - weight)[:, None]
    position += track["position"][high] * weight[:, None]
    velocity = track["velocity"][low] * (1 - weight)[:, None]
    velocity += track["velocity"][high] * weight[:, None]
    return position, velocity


def track_score(single, track, receiver, up, eta, include_evaluation=False):
    position, velocity = interpolate(track, eta)
    delta = position - receiver
    distance = np.linalg.norm(delta, axis=1)
    visible = bool(np.max(np.sum(delta * up, axis=1) / distance) >= 0)
    prediction = (
        -single.REFERENCE_RF_HZ / single.LIGHT_KM_S * np.sum(delta * velocity, axis=1) / distance
    )
    training = track["training_mask"]
    residual = track["measured_hz"] - prediction
    cfo = float(np.mean(residual[training]))
    error = residual - cfo
    train_rms = float(np.sqrt(np.mean(error[training] ** 2))) if visible else 800.0
    row = {
        "session_id": track["session_id"],
        "track_id": track["track_id"],
        "candidate_id": track["candidate_id"],
        "frequency_offset_hz": cfo,
        "training_rms_hz": train_rms,
        "weight_s": track["weight_s"],
        "visible": visible,
    }
    if include_evaluation:
        row["evaluation_rms_hz"] = (
            float(np.sqrt(np.mean(error[~training] ** 2))) if visible else 800.0
        )
    return row


def score(single, tracks, point, etas, scale, include_evaluation=False):
    receiver, up = single.receiver_ecef(*point)
    rows = [
        track_score(single, track, receiver, up, etas["global"], include_evaluation)
        for track in tracks
    ]
    total = sum(row["weight_s"] for row in rows)
    capped = sum(row["weight_s"] * min(800.0, row["training_rms_hz"]) ** 2 for row in rows)
    uncapped = sum(row["weight_s"] * row["training_rms_hz"] ** 2 for row in rows)
    penalty = 800.0**2 * sum((value / scale) ** 2 for value in etas.values())
    return {
        "penalized_objective_rmse_hz": float(np.sqrt((capped + penalty) / total)),
        "training_capped800_rmse_hz": float(np.sqrt(capped / total)),
        "training_uncapped_rmse_hz": float(np.sqrt(uncapped / total)),
        "visibility_failure_count": sum(not row["visible"] for row in rows),
        "rows": rows,
    }


def centered_residual(single, track, point, eta):
    receiver, _ = single.receiver_ecef(*point)
    position, velocity = interpolate(track, eta)
    delta = position - receiver
    distance = np.linalg.norm(delta, axis=1)
    prediction = (
        -single.REFERENCE_RF_HZ / single.LIGHT_KM_S * np.sum(delta * velocity, axis=1) / distance
    )
    mask = track["training_mask"]
    residual = track["measured_hz"][mask] - prediction[mask]
    return residual - residual.mean()


def bound_active_schur_step(hpp, gp, blocks, etas, tolerance=0.002):
    frozen = set()
    while True:
        schur, right = hpp.copy(), -gp.copy()
        for key, (d, q, g) in blocks.items():
            if key not in frozen:
                schur -= np.outer(q, q) / d
                right += q * g / d
        dp = np.linalg.solve(schur, right)
        de = {
            key: 0.0 if key in frozen else float((-g - q @ dp) / d)
            for key, (d, q, g) in blocks.items()
        }
        outward = {
            key
            for key, value in etas.items()
            if (value <= -5.0 + tolerance and de[key] < 0)
            or (value >= 5.0 - tolerance and de[key] > 0)
        }
        updated = frozen | outward
        if updated == frozen:
            return dp, de, tuple(sorted(frozen))
        frozen = updated


def projected_gradient_norm(gp, blocks, etas, tolerance=0.002):
    values = list(gp)
    for key, (_d, _q, gradient) in blocks.items():
        value = etas[key]
        if value <= -5.0 + tolerance:
            gradient = min(gradient, 0.0)
        elif value >= 5.0 - tolerance:
            gradient = max(gradient, 0.0)
        values.append(gradient)
    return float(np.linalg.norm(values, ord=np.inf))


def coupled_polish(single, tracks, prior, position, etas, scale):
    centre, trace = prior[:2], []
    for iteration in range(1, 51):
        point = single.offset_coordinate(centre, *position)
        current = score(single, tracks, point, etas, scale)
        active = {row["track_id"]: row["training_rms_hz"] < 800 for row in current["rows"]}
        hpp, gp = np.zeros((2, 2)), np.zeros(2)
        penalty = 800.0**2 / scale**2
        blocks = {key: [penalty, np.zeros(2), penalty * value] for key, value in etas.items()}
        for track in tracks:
            if not active[track["track_id"]]:
                continue
            sat, eta = "global", etas["global"]
            residual = centered_residual(single, track, point, eta)
            columns = []
            for axis in range(2):
                plus, minus = position.copy(), position.copy()
                plus[axis] += 0.1
                minus[axis] -= 0.1
                columns.append(
                    (
                        centered_residual(
                            single, track, single.offset_coordinate(centre, *plus), eta
                        )
                        - centered_residual(
                            single, track, single.offset_coordinate(centre, *minus), eta
                        )
                    )
                    / 0.2
                )
            a = np.column_stack(columns)
            lo, hi = max(-5.0, eta - 0.01), min(5.0, eta + 0.01)
            b = (
                centered_residual(single, track, point, hi)
                - centered_residual(single, track, point, lo)
            ) / (hi - lo)
            weight = track["weight_s"] / len(residual)
            hpp += weight * a.T @ a
            gp += weight * a.T @ residual
            blocks[sat][0] += weight * float(b @ b)
            blocks[sat][1] += weight * (a.T @ b)
            blocks[sat][2] += weight * float(b @ residual)
        schur, right = hpp.copy(), -gp.copy()
        for d, q, g in blocks.values():
            schur -= np.outer(q, q) / d
            right += q * g / d
        try:
            dp, de, frozen = bound_active_schur_step(hpp, gp, blocks, etas)
        except np.linalg.LinAlgError:
            trace.append({"iteration": iteration, "accepted": False, "reason": "singular"})
            break
        gradient_norm = projected_gradient_norm(gp, blocks, etas)
        accepted = False
        for fraction in (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125):
            trial_position = position + fraction * dp
            if np.hypot(*trial_position) > prior[2]:
                continue
            raw_etas = {key: value + fraction * de[key] for key, value in etas.items()}
            if any(value < -5.0 or value > 5.0 for value in raw_etas.values()):
                continue
            trial_etas = {key: float(value) for key, value in raw_etas.items()}
            trial = score(
                single, tracks, single.offset_coordinate(centre, *trial_position), trial_etas, scale
            )
            if (
                trial["visibility_failure_count"] == 0
                and trial["penalized_objective_rmse_hz"] < current["penalized_objective_rmse_hz"]
            ):
                gain = current["penalized_objective_rmse_hz"] - trial["penalized_objective_rmse_hz"]
                position, etas, accepted = trial_position, trial_etas, True
                trace.append(
                    {
                        "iteration": iteration,
                        "accepted": True,
                        "objective_rmse_hz": trial["penalized_objective_rmse_hz"],
                        "fraction": fraction,
                        "position_step_km": float(np.linalg.norm(fraction * dp)),
                        "maximum_tau_step_s": float(
                            max(abs(fraction * value) for value in de.values())
                        ),
                        "bound_active_scans": list(frozen),
                        "projected_gradient_inf": gradient_norm,
                    }
                )
                if gain < 0.001 or (
                    np.linalg.norm(fraction * dp) < 0.01
                    and max(abs(fraction * x) for x in de.values()) < 0.002
                ):
                    return position, etas, trace, True, "stopping_rule_satisfied"
                break
        if not accepted:
            trace.append({"iteration": iteration, "accepted": False, "reason": "backtrack"})
            break
    reason = trace[-1].get("reason", "iteration_limit") if trace else "iteration_limit"
    return position, etas, trace, False, reason


def fit_arm(single, tracks, prior_name, baseline, scale):
    prior = single.PRIORS[prior_name]
    centre = prior[:2]
    position = np.asarray([baseline["selected"]["east_km"], baseline["selected"]["north_km"]])
    satellites = ["global"]
    grouped = {"global": tracks}
    etas = {satellite: 0.0 for satellite in satellites}

    def point():
        return single.offset_coordinate(centre, position[0], position[1])

    trace = []
    previous = score(single, tracks, point(), etas, scale)["penalized_objective_rmse_hz"]
    for iteration in range(1, 6):
        receiver, up = single.receiver_ecef(*point())
        scalar_nfev = 0
        scalar_failures = 0
        for satellite in satellites:

            def satellite_loss(value, selected=satellite, fixed_receiver=receiver, fixed_up=up):
                rows = [
                    track_score(single, track, fixed_receiver, fixed_up, value)
                    for track in grouped[selected]
                ]
                data = sum(
                    row["weight_s"] * min(800.0, row["training_rms_hz"]) ** 2 for row in rows
                )
                return data + 800.0**2 * (value / scale) ** 2

            candidate = minimize_scalar(
                satellite_loss,
                bounds=(-5.0, 5.0),
                method="bounded",
                options={"xatol": 0.002, "maxiter": 40},
            )
            scalar_nfev += int(candidate.nfev)
            scalar_failures += int(not candidate.success)
            if candidate.fun < satellite_loss(etas[satellite]):
                etas[satellite] = float(candidate.x)

        def position_loss(values):
            if np.hypot(*values) > prior[2]:
                return 1e6 + np.hypot(*values) - prior[2]
            trial = single.offset_coordinate(centre, values[0], values[1])
            return score(single, tracks, trial, etas, scale)["penalized_objective_rmse_hz"]

        fit = minimize(
            position_loss,
            position,
            method="Powell",
            bounds=[(-prior[2], prior[2]), (-prior[2], prior[2])],
            options={"maxfev": 100, "xtol": 0.02, "ftol": 1e-5},
        )
        if fit.fun < position_loss(position):
            position = np.asarray(fit.x)
        current = score(single, tracks, point(), etas, scale)["penalized_objective_rmse_hz"]
        trace.append(
            {
                "iteration": iteration,
                "objective_rmse_hz": current,
                "position_success": bool(fit.success),
                "position_evaluations": int(fit.nfev),
                "scalar_evaluations": scalar_nfev,
                "scalar_failures": scalar_failures,
            }
        )
        if previous - current < 0.01:
            break
        previous = current
    position, etas, polish_trace, stopping_rule_satisfied, polish_stop_reason = coupled_polish(
        single, tracks, prior, position, etas, scale
    )
    final = score(single, tracks, point(), etas, scale)
    return {
        "prior": prior_name,
        "scale_s": scale,
        "latitude_deg": point()[0],
        "longitude_deg": point()[1],
        "east_km": float(position[0]),
        "north_km": float(position[1]),
        "global_tau_s": etas["global"],
        "tau_boundary_count": int(
            sum(np.isclose(abs(value), 5.0, atol=0.002) for value in etas.values())
        ),
        "active_tau_count": sum(abs(value) >= 0.01 for value in etas.values()),
        "scan_count": len({track["session_id"] for track in tracks}),
        "iterations": len(trace),
        "trace": trace,
        "polish_iterations": len(polish_trace),
        "polish_trace": polish_trace,
        "stopping_rule_satisfied": stopping_rule_satisfied,
        "polish_stop_reason": polish_stop_reason,
        **{key: value for key, value in final.items() if key != "rows"},
        "fixed_tracks": final["rows"],
    }


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    single = load_module(args.single_tool, "full8h_shared_epoch_single")
    baseline_multi = json.loads(args.baseline_multi.read_text())
    baseline_full = json.loads(args.baseline_full.read_text())
    manifest = json.loads(args.manifest.read_text())
    sessions = manifest["source_group"]["session_ids"]
    if len(sessions) != 72 or baseline_full["session_ids"] != sessions:
        raise ValueError("baseline sessions must exactly match frozen 72-scan TRAIN cohort")
    views = {view["scan_count"]: view for view in baseline_multi["views"]}
    if set(views) != {6, 16} or any(views[n]["session_ids"] != sessions[:n] for n in views):
        raise ValueError("nested baselines must exactly match frozen TRAIN prefixes")
    baseline_bindings = {row["session_id"]: row for row in baseline_full["bindings"]["sessions"]}
    if set(baseline_bindings) != set(sessions):
        raise ValueError("baseline cache bindings do not exactly cover frozen cohort")
    for session_id in sessions:
        directory = args.cache_root / session_id
        receipt_path = directory / "cache_receipt.json"
        cache_path = directory / "state_cache.npz"
        receipt = json.loads(receipt_path.read_text())
        expected = baseline_bindings[session_id]
        if receipt["session_id"] != session_id:
            raise ValueError("cache receipt session mismatch")
        if digest(receipt_path) != expected["receipt"] or digest(cache_path) != expected["cache"]:
            raise ValueError("cache content differs from sealed baseline binding")
    started = time.monotonic()
    definitions = [(6, views[6]), (16, views[16]), (72, baseline_full)]
    arms, parity, all_bindings = [], [], {}
    prepared = {}
    for count, view in definitions:
        for baseline_search in view["searches"]:
            tracks, current_bindings = prepare(
                single, args.cache_root, sessions[:count], baseline_search["selected"]["scans"]
            )
            prepared[(count, baseline_search["prior"])] = tracks
            all_bindings[str(count)] = current_bindings
            point = (
                baseline_search["selected"]["latitude_deg"],
                baseline_search["selected"]["longitude_deg"],
            )
            base = score(single, tracks, point, {"global": 0.0}, 1.0)
            parity.append(
                {
                    "scan_count": count,
                    "prior": baseline_search["prior"],
                    **{key: value for key, value in base.items() if key != "rows"},
                }
            )
            for scale in SCALES:
                arm = fit_arm(single, tracks, baseline_search["prior"], baseline_search, scale)
                arm["scan_count"] = count
                arms.append(arm)
    inference = {
        "schema": "conditional-nested-global-epoch-position/v1",
        "position_truth_used": False,
        "reserved_rows_used": False,
        "session_ids": sessions,
        "scales_s": SCALES,
        "baseline_parity": parity,
        "arms": arms,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "manifest": digest(args.manifest),
            "baseline_multi": digest(args.baseline_multi),
            "baseline_full": digest(args.baseline_full),
            "single_tool": digest(args.single_tool),
            "tool": digest(Path(__file__)),
            "caches": all_bindings,
        },
    }
    args.output.mkdir(parents=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )
    results = json.loads(payload)
    for arm in results["arms"]:
        tracks = prepared[(arm["scan_count"], arm["prior"])]
        held = score(
            single,
            tracks,
            (arm["latitude_deg"], arm["longitude_deg"]),
            {"global": arm["global_tau_s"]},
            arm["scale_s"],
            True,
        )
        total = sum(row["weight_s"] for row in held["rows"])
        arm["reserved_capped800_rmse_hz"] = float(
            np.sqrt(
                sum(
                    row["weight_s"] * min(800.0, row["evaluation_rms_hz"]) ** 2
                    for row in held["rows"]
                )
                / total
            )
        )
        arm["reserved_uncapped_rmse_hz"] = float(
            np.sqrt(
                sum(row["weight_s"] * row["evaluation_rms_hz"] ** 2 for row in held["rows"]) / total
            )
        )
        arm["reference_error_km"] = single.haversine_km(
            (arm["latitude_deg"], arm["longitude_deg"]), single.REFERENCE
        )
    results["reference_coordinate"] = {
        "latitude_deg": single.REFERENCE[0],
        "longitude_deg": single.REFERENCE[1],
        "role": "post-seal only",
    }
    (args.output / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--baseline-multi", type=Path, required=True)
    parser.add_argument("--baseline-full", type=Path, required=True)
    parser.add_argument("--single-tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
