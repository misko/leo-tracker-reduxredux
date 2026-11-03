"""Oracle-position diagnostics only: never imported by fitting or selection."""

import json

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_joint_exact_mean import exact_conditional_frequency
from investigate_dsx01_localization_failures import OUTPUT, DiagnosticNormal
from prototype_dsx01_continuous_position import latlon
from report_dsx01_radial_restarts import truth_position
from run_dsx01_clean_region import load_scan
from run_dsx01_joint_descent import ARMS, CASES, hypothesis_bank

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency


def objective_parts(p, x):
    r = p.calculate(x)
    prior = r["coefficient"]**2
    nb, ns, nj = p.hardware.shape[1], p.smooth.shape[1], len(p.labels)
    parts = dict(
        frequency_data=float(np.sum(
            r["noise_precision"][p.noise_groups]
            * (r["conditional_residual_hz"] / p.point_noise)**2)),
        receiver_offset_prior=float(prior[:4].sum()),
        receiver_linear_prior=float(prior[4:8].sum()),
        c_prior=float(prior[8:nb].sum()),
        receiver_smooth_prior=float(prior[nb:nb + ns].sum()),
        satellite_phase_prior=float(prior[nb + ns:nb + ns + nj].sum()),
        satellite_orbit_prior=float(prior[nb + ns + nj:-len(p.members)].sum()),
        track_constant_prior=float(prior[-len(p.members):].sum()),
        nuisance_logvolume=float(r["logvolume"]), noise_gamma=float(r["noise_gamma_cost"]),
        diagonal_noise_volume=float(p.noise_volume),
        visibility=float(np.sum((np.maximum(0, -r["elevation"]) / 2)**2)))
    residual = p.residual(x)
    if abs(sum(parts.values()) - residual @ residual) > 1e-6:
        raise ValueError("objective decomposition does not replay")
    family = []
    for local, j in enumerate(p.labels):
        use = p.flat_labels == local
        constants = sum(prior[-len(p.members) + k]
                        for k, row in enumerate(p.rows) if row["candidate_index"] == j)
        orbit = 0.
        if j in p.supported:
            k = p.supported.index(j)
            start = nb + ns + nj + 3 * k
            orbit = float(prior[start:start + 3].sum())
        family.append(dict(
            norad=int(p.scan.norads[j]),
            weighted_frequency_cost=float(np.sum(r["noise_precision"][p.noise_groups[use]]
                                                 * (r["conditional_residual_hz"][use]
                                                    / p.point_noise[use])**2)),
            phase_prior=float(prior[nb + ns + local]), orbit_prior=orbit,
            track_constant_prior=float(constants)))
    return r, parts, family


def linear_information(p, x, calculated):
    coefficient = calculated["coefficient"]
    derivatives = []
    for offset in np.eye(2) * 0.001:
        means = []
        for point in (np.asarray(x) - offset, np.asarray(x) + offset):
            r = p.calculate(point)
            means.append(p.q * r["intercept"] + r["features"] @ coefficient)
        derivatives.append((means[1] - means[0]) / .002)
    root_weight = np.sqrt(calculated["noise_precision"][p.noise_groups]) / p.point_noise
    design = calculated["features"] * root_weight[:, None]
    geometry = np.array(derivatives).T * root_weight[:, None]
    gram = np.eye(design.shape[1]) + design.T @ design
    correction = design.T @ geometry
    information = geometry.T @ geometry - correction.T @ np.linalg.solve(gram, correction)
    raw = geometry.T @ geometry
    values, vectors = np.linalg.eigh(information)
    return dict(information=information, raw_position_information=raw,
                eigenvalues=values, eigenvectors=vectors,
                information_trace_fraction=float(np.trace(information) / np.trace(raw)),
                interpretation=("local Gaussian tangent information conditional on labels/noise "
                                "precisions; engineering priors, "
                                "not calibrated position confidence"))


def run():
    for case in CASES:
        scan, sigma = load_scan(case)
        nodes, _ = hypothesis_bank(scan, sigma)
        source = json.loads((OUTPUT / case / "core.json").read_text())
        original = json.loads((OUTPUT.parent / "2026_10_18_dsx01_joint_descent"
                               / case / "start_00.json").read_text())
        node = nodes[original["arms"]["c0"]["final_mode"]]
        arms = {}
        for arm in ARMS:
            saved = source["arms"][arm]
            p = DiagnosticNormal(scan, node, sigma, arm == "fitted_c", reference=saved["reference"])
            endpoint = saved["refreshed"]["parameters"]
            evaluated = {}
            for name, point in (("blind", endpoint), ("GPS_diagnostic_only", truth_position())):
                r, parts, family = objective_parts(p, point)
                nominal = paired_phase_frequency(p.sky, p.flat_times, p.flat_labels,
                                                 np.zeros(len(p.labels)), *latlon(point))[0]
                nb, ns = p.hardware.shape[1], p.smooth.shape[1]
                coefficient = r["coefficient"]
                radio_and_constant = (r["features"][:, :nb + ns] @ coefficient[:nb + ns]
                                      + r["features"][:, -len(p.members):]
                                      @ coefficient[-len(p.members):])
                evaluated[name] = dict(
                    point=point, parts=parts, families=family,
                    conditional_residual_hz=r["conditional_residual_hz"],
                    total_prediction_hz=p.values - r["conditional_residual_hz"],
                    nominal_orbit_plus_conditional_calibration_hz=(
                        p.q * nominal + radio_and_constant),
                    coefficient=r["coefficient"], noise_precision=r["noise_precision"])
            approximation = {}
            for stage, reference, point in (("zero_expansion", None,
                                             saved["baseline"]["parameters"]),
                                             ("refreshed", saved["reference"], endpoint)):
                q = DiagnosticNormal(scan, node, sigma, arm == "fitted_c", reference=reference)
                exact, _, parameters = exact_conditional_frequency(q, point)
                tangent, _ = q.conditional_frequency(point)
                delta = (exact - tangent) * q.q
                approximation[stage] = dict(
                    exact_minus_tangent_hz=delta,
                    rms_hz=float(np.sqrt(np.mean(delta**2))),
                    physical_parameters=parameters,
                    max_abs_hz=float(np.max(abs(delta))))
            arms[arm] = dict(evaluated=evaluated, approximation=approximation,
                             information=linear_information(p, endpoint, p.calculate(endpoint)),
                             point_noise_hz=p.point_noise, alias_lifted_values_hz=p.values)
        write(OUTPUT / case / "postfit_diagnostics.json", dict(
            case=case, arms=arms, GPS_used_for_diagnostics_only=True,
            GPS_never_used_for_updates_model_selection_or_satellite_labels=True,
            this_file_forbidden_as_inference_input=True))
        print(case, "postfit diagnostics complete", flush=True)


if __name__ == "__main__":
    run()
