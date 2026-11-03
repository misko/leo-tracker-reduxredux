import hashlib
import json
import time

import numpy as np
from anchors import select_anchors
from association import associate
from common import ROOT, SOURCE, TRACK_SOURCE, Data, circular, coordinates, ecef, jsonable, rho
from refinement import fit_fixed


def save(name, value):
    (ROOT / name).write_text(json.dumps(jsonable(value), indent=2, allow_nan=False) + "\n")


def require_success(fitted):
    if not fitted["success"] or not np.isfinite(fitted["objective"]):
        raise RuntimeError(f"Refusing to propagate unsuccessful fit: {fitted['message']}")
    return fitted


def converged_best(fits):
    successful = [fit for fit in fits if fit["success"] and np.isfinite(fit["objective"])]
    if not successful:
        raise RuntimeError("No anchor start converged")
    return min(successful, key=lambda fit: fit["objective"])


def validate_assignments(data, assignments):
    rows = np.asarray(assignments["rows"], dtype=int)
    satellites = np.asarray(assignments["satellites"], dtype=int)
    weights = np.asarray(assignments["weights"], dtype=float)
    if not len(rows):
        raise ValueError("No usable coherent associations; refusing to invent a solution")
    assert rows.shape == satellites.shape == weights.shape
    assert len(np.unique(data.group[rows])) == len(rows)
    assert np.all(np.isfinite(weights)) and np.all(weights > 0)


def diagnostics(data, parameters, assignments):
    prediction, visible = data.predict(parameters)
    residual = np.abs(circular(data.measured[:, None], prediction))
    residual[~visible] = np.inf
    best = np.min(residual, axis=1)
    group_errors = np.full(int(data.group.max()) + 1, np.inf)
    np.minimum.at(group_errors, data.group, best)
    rows = np.asarray(assignments["rows"], dtype=int)
    satellites = np.asarray(assignments["satellites"], dtype=int)
    selected = circular(data.measured[rows], prediction[rows, satellites])
    accepted = visible[rows, satellites] & (np.abs(selected) < 1000)
    summary = {
        "all_group_nearest_curve_loss_diagnostic_only": float(np.mean(rho(group_errors))),
        "all_group_nearest_within_1000hz": int(np.sum(group_errors < 1000)),
        "assigned_groups": len(rows),
        "assigned_visible_within_1000hz": int(accepted.sum()),
        "assigned_median_abs_error_hz": float(np.median(np.abs(selected))),
        "assigned_weighted_rms_hz": float(
            np.sqrt(np.average(selected**2, weights=assignments["weights"]))
        ),
        "effective_weight": float(np.sum(assignments["weights"])),
        "assigned_satellites": len(np.unique(satellites)),
        "rx_parameters": parameters[2:6],
        "maximum_absolute_shift_s": float(np.max(np.abs(parameters[6:]))),
        "satellite_support": [],
    }
    for satellite in np.unique(satellites):
        mask = satellites == satellite
        selected_times = np.sort(np.unique(data.times[rows[mask & accepted]]))
        support = float(np.sum(np.minimum(np.diff(selected_times), 1)))
        summary["satellite_support"].append(
            {
                "catalog_number": int(data.numbers[satellite]),
                "assigned_groups": int(mask.sum()),
                "within_1000hz": int((mask & accepted).sum()),
                "supported_duration_s_capped_1s_gaps": support,
                "shift_s": float(parameters[6 + satellite]),
            }
        )
    return summary


def main():
    started = time.monotonic()
    data = Data()
    result = {
        "session_id": data.session_id,
        "protocol": {
            "data": "8841 exported gate-passing GLRT alternatives, 3192 exclusive source groups",
            "evaluation": "all data for fitting; reference coordinates used only after fits",
            "scope": (
                "conditional on previous position/RX initialization and frozen 64-satellite pool"
            ),
            "parameters": "east,north,a0,b0,a1,b1,64 satellite shifts; altitude zero",
            "selection": "whole-track anchors then coherent extension; observed CFO never replaced",
            "weights": (
                "component-defined time-balanced weights; extension weight capped by anchors"
            ),
            "timing": "fixed-association ablation; sigma1s,bounds3s; support-gated shifts",
            "resource_policy": "single numerical thread; sequential bounded fits; no RF collection",
            "validation": "local prototype, not blind localization or calibrated uncertainty",
        },
        "join": data.join_receipt,
        "input_sha256": {
            str(path.relative_to(ROOT.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                SOURCE / "inputs.npz",
                SOURCE / "inputs.json",
                SOURCE / "satellite-time-states-10s.npz",
                TRACK_SOURCE / "inputs.npz",
            ]
        },
        "stages": {},
    }
    anchors = select_anchors(data, data.initial, max_tracks=12)
    validate_assignments(data, anchors)
    save("anchors.json", anchors)
    print(
        json.dumps(
            {
                "anchor_groups": len(anchors["rows"]),
                "anchor_satellites": len(np.unique(anchors["satellites"])),
            }
        ),
        flush=True,
    )
    fits = []
    for offset in ([0, 0], [5, -5]):
        initial = data.initial.copy()
        initial[:2] += offset
        fits.append(fit_fixed(data, anchors, initial, timing=False, max_nfev=160))
    anchor_fit = converged_best(fits)
    parameters = np.asarray(anchor_fit["parameters"])
    result["anchor_starts"] = fits
    result["stages"]["anchors"] = {
        "fit": anchor_fit,
        "metrics": diagnostics(data, parameters, anchors),
    }
    save("results.json", result)
    print(
        json.dumps(jsonable({"stage": "anchors", **result["stages"]["anchors"]["metrics"]})),
        flush=True,
    )
    extension_iterations = []
    previous_keys = None
    result["association_converged"] = False
    for iteration in range(6):
        associations = associate(data, parameters, anchors)
        validate_assignments(data, associations)
        for row, satellite in zip(anchors["rows"], anchors["satellites"], strict=True):
            matches = np.flatnonzero(data.group[associations["rows"]] == data.group[row])
            assert len(matches) == 1 and associations["satellites"][matches[0]] == satellite
        fitted = require_success(
            fit_fixed(data, associations, parameters, timing=False, max_nfev=160)
        )
        parameters = np.asarray(fitted["parameters"])
        keys = set(
            zip(
                data.group[associations["rows"]].tolist(),
                np.asarray(associations["satellites"]).tolist(),
                strict=True,
            )
        )
        summary = {
            "iteration": iteration,
            "fit": fitted,
            "metrics": diagnostics(data, parameters, associations),
            "changed_group_satellite_pairs": None
            if previous_keys is None
            else len(keys.symmetric_difference(previous_keys)),
        }
        extension_iterations.append(summary)
        save("extension-iterations.json", extension_iterations)
        print(
            json.dumps(jsonable({"stage": f"extension_{iteration}", **summary["metrics"]})),
            flush=True,
        )
        if previous_keys == keys:
            result["association_converged"] = True
            break
        previous_keys = keys
    save("extensions.json", associations)
    result["stages"]["extensions"] = {"fit": fitted, "metrics": summary["metrics"]}
    result["extension_iterations"] = extension_iterations
    save("results.json", result)
    timed = require_success(
        fit_fixed(data, associations, parameters, timing=True, sigma_s=1, bound_s=3, max_nfev=200)
    )
    result["stages"]["timing"] = {
        "fit": timed,
        "metrics": diagnostics(data, np.asarray(timed["parameters"]), associations),
    }
    post_timing = associate(data, np.asarray(timed["parameters"]), anchors)
    validate_assignments(data, post_timing)
    targeted_rows = post_timing["rows"][
        (data.numbers[post_timing["satellites"]] == 66891)
        & (data.receiver[post_timing["rows"]] == 0)
        & (data.channel[post_timing["rows"]] == 1)
    ]
    targeted_times = data.times[targeted_rows]
    result["post_timing_association_diagnostic"] = {
        "purpose": "Post-timing association only: no refit, not a fourth fitted model",
        "groups": len(post_timing["rows"]),
        "channel1_rx0_66891": {
            "groups": len(targeted_times),
            "start_s": float(targeted_times.min()) if len(targeted_times) else None,
            "end_s": float(targeted_times.max()) if len(targeted_times) else None,
            "before_200s": int(np.sum(targeted_times < 200)),
        },
        "diagnostics": post_timing["diagnostics"],
    }
    save("post-timing-association-diagnostic.json", result["post_timing_association_diagnostic"])
    save("results.json", result)
    print(
        json.dumps(jsonable({"stage": "timing", **result["stages"]["timing"]["metrics"]})),
        flush=True,
    )
    support = [
        (
            np.sum(np.asarray(anchors["weights"])[np.asarray(anchors["satellites"]) == satellite]),
            int(satellite),
        )
        for satellite in np.unique(anchors["satellites"])
    ]
    result["anchor_sensitivity"] = []
    for _, satellite in sorted(support, reverse=True)[:2]:
        mask = np.asarray(anchors["satellites"]) != satellite
        reduced = {key: np.asarray(anchors[key])[mask] for key in ("rows", "satellites", "weights")}
        if not len(reduced["rows"]):
            continue
        sensitivity = fit_fixed(
            data, reduced, np.asarray(anchor_fit["parameters"]), timing=False, max_nfev=160
        )
        result["anchor_sensitivity"].append(
            {
                "removed_catalog_number": int(data.numbers[satellite]),
                "fit": sensitivity,
                "position_change_km": float(
                    np.linalg.norm(
                        np.asarray(sensitivity["parameters"])[:2]
                        - np.asarray(anchor_fit["parameters"])[:2]
                    )
                ),
            }
        )
    reference = json.loads((SOURCE / "inputs.json").read_text())["source"]["reference_site"]
    reference_position = ecef(reference["latitude_deg"], reference["longitude_deg"])
    for stage in result["stages"].values():
        latitude, longitude = coordinates(np.asarray(stage["fit"]["parameters"])[:2])
        stage["reference_error_km"] = float(
            np.linalg.norm(ecef(latitude, longitude) - reference_position)
        )
        stage["latitude"], stage["longitude"] = float(latitude), float(longitude)
    result["elapsed_s"] = time.monotonic() - started
    save("results.json", result)
    print(
        json.dumps(
            {
                "reference_error_km": {
                    name: stage["reference_error_km"] for name, stage in result["stages"].items()
                },
                "elapsed_s": result["elapsed_s"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
