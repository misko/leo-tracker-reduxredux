"""Radio-only drift information conditional on existing curved-family hypotheses.

No orbit shape or evaluation GPS enters the design. These are diagnostics,
not new calibration priors: feeding them back to the same data would count
information twice unless the joint likelihood were factored appropriately.
"""

import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import ROOT, Scan
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import measurement_path
from run_dsx01_joint_marginal import OUTPUT as BASE

from leo.analysis.research.orbit_uncertainty import project_constant_features
from leo.analysis.research.retained_track_likelihood import PERIOD

OUTPUT = ROOT / "reports/2026_10_18_dsx01_radio_drift_information"


def quartic_basis(times):
    t = np.asarray(times)
    z = (t - 150) / 150
    return np.column_stack(
        (
            np.vander(z, 5, increasing=True),
            *[np.maximum(0, (t - knot) / 150) ** 4 for knot in (60, 120, 180, 240)],
        )
    )


def remove_family(raw, hardware, family):
    y, a, b = np.asarray(raw), np.asarray(hardware), np.asarray(family)
    if y.ndim != 1 or a.shape[0] != len(y) or b.shape[0] != len(y):
        raise ValueError("matching data, hardware and family design rows required")
    q, singular, _ = np.linalg.svd(b, full_matrices=False)
    rank = int(np.sum(singular > max(1e-12, singular[0] * 1e-9)))
    q = q[:, :rank]
    return y - q @ (q.T @ y), a - q @ (q.T @ a), rank


def information(design, data, targets):
    a, y = np.asarray(design), np.asarray(data)
    u, singular, vt = np.linalg.svd(a, full_matrices=False)
    keep = singular > max(1e-10, singular[0] * 1e-9)
    estimate = vt[keep].T @ ((u[:, keep].T @ y) / singular[keep])
    covariance = (vt[keep].T / singular[keep] ** 2) @ vt[keep]
    result = {}
    for name, vector in targets.items():
        v = np.asarray(vector)
        unidentifiable = bool(np.linalg.norm(vt[~keep] @ v) > 1e-7 * max(1.0, np.linalg.norm(v)))
        result[name] = dict(
            identifiable=not unidentifiable,
            estimate=None if unidentifiable else float(v @ estimate),
            nominal_sigma=None if unidentifiable else float(np.sqrt(max(0, v @ covariance @ v))),
        )
    return dict(
        rank=int(keep.sum()),
        singular_values=singular,
        estimate=estimate,
        target_information=result,
        residual_square=float(np.sum((y - a @ estimate) ** 2)),
    )


def run():
    OUTPUT.mkdir(exist_ok=True)
    results, bindings = {}, {}
    for case in (f"DSX01-S0{k}" for k in range(1, 6)):
        source = BASE / case / "robust/endpoints.json"
        fit = json.loads(source.read_text())["fits"]["c0"]
        bindings[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
        scan = Scan(case)
        apply_measurements(
            scan, json.loads(measurement_path(case).read_text())["points"], "glrt300"
        )
        by_component = {t["key"]: i for i, t in enumerate(scan.tracks)}
        sigma = fit["diagnostics"]["noise_sigma_hz"]
        case_results = {}
        for arm in ("c0", "fitted_c"):
            width = 8 + int(arm == "fitted_c")
            groups = {}
            n = 0
            for row, alias in zip(fit["rows"], fit["aliases"], strict=True):
                i = by_component[row["component"]]
                assert i in scan.curved
                t = scan.tracks[i]
                times = t["times"]
                g = 2 * (t["receiver"] - 1) + int(t["channel"] > 4)
                hardware = np.zeros((len(times), width))
                hardware[:, g], hardware[:, 4 + g] = 1.0, times - 150
                if width == 9:
                    hardware[:, -1] = t["rf_hz"] / 1e9 - 11.5
                family = t["rf_hz"] / 11.5e9 * quartic_basis(times)
                raw, design, _ = project_constant_features(
                    t["values"] + alias * PERIOD,
                    np.column_stack((hardware, family)),
                    np.eye(len(times)) / sigma,
                )
                groups.setdefault(row["candidate_index"], []).append(
                    (raw, design[:, :width], design[:, width:])
                )
                n += len(times)
            data, designs, family_rank = [], [], 0
            for items in groups.values():
                raw = np.concatenate([r[0] for r in items])
                hardware = np.vstack([r[1] for r in items])
                family = np.vstack([r[2] for r in items])
                y, a, rank = remove_family(raw, hardware, family)
                data.append(y)
                designs.append(a)
                family_rank += rank
            targets = {}
            for g, label in enumerate(("RX1_low", "RX1_high", "RX2_low", "RX2_high")):
                vector = np.zeros(width)
                vector[4 + g] = 1.0
                targets[label + "_Hz_s"] = vector
            for rx in range(2):
                vector = np.zeros(width)
                vector[4 + 2 * rx : 6 + 2 * rx] = 0.5
                targets[f"RX{rx + 1}_mean_Hz_s"] = vector
                contrast = np.zeros(width)
                contrast[4 + 2 * rx : 6 + 2 * rx] = [-0.5, 0.5]
                targets[f"RX{rx + 1}_half_high_minus_low_Hz_s"] = contrast
            common, relative = np.zeros(width), np.zeros(width)
            common[4:8], relative[4:8] = 0.25, [-0.5, -0.5, 0.5, 0.5]
            targets["common_RX_mean_Hz_s"] = common
            targets["RX2_minus_RX1_mean_Hz_s"] = relative
            result = information(np.vstack(designs), np.concatenate(data), targets)
            dof = n - family_rank - result["rank"]
            result.update(
                original_curved_points=n,
                family_basis_rank=family_rank,
                residual_dof=dof,
                standardized_radio_model_RMS=float(
                    np.sqrt(result["residual_square"] / max(1, dof))
                ),
                noise_sigma_hz=sigma,
                no_information_fed_back_to_localization=True,
            )
            case_results[arm] = result
        results[case] = case_results
    write(OUTPUT / "information.json", results)
    write(
        OUTPUT / "protocol.json",
        dict(
            GPS_or_orbit_shape_used=False,
            curved_family_labels_are_unverified_blind_hypotheses=True,
            family_model="RF-scaled C3-continuous piecewise quartic, knots 60/120/180/240 s",
            fixed_curve_constant_sigma_hz=1000.0,
            no_hardware_prior=True,
            known_radio_noise_and_curve_constant_covariance_assumed=True,
            same_points_labels_aliases_noise_and_polynomials_in_both_c_arms=True,
            numerical_rank_relative_threshold=1e-9,
            numerical_rank_absolute_threshold=1e-10,
            model_residual_RMS_must_be_reviewed_before_interpreting_information=True,
            information_is_not_a_new_independent_prior=True,
            inputs_sha256=bindings,
        ),
    )
    print(json.dumps(dict(scans=len(results), diagnostics_only=True)), flush=True)


if __name__ == "__main__":
    run()
