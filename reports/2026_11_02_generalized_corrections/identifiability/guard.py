"""Conservative, report-local other-family RF displacement guard.

No position optimization, learned precision, fitted hardware, GPS, or saved
phase reference enters this diagnostic. The endpoint geometry is linearized at
zero absolute phase and all nuisance coefficients are projected jointly. This
can remove real position information: abstention is not evidence of a wrong
satellite identity. The cutoffs are engineering gates, not significance levels.
"""
import hashlib
import json

import numpy as np


POLICY = dict(
    version="other_family_union_projection_v1",
    noise_sigma_hz=150.0,
    minimum_other_families=3,
    minimum_displacement_information=4.0,
    minimum_projected_RF_gain=4.0,
    minimum_leave_one_family_out_information=1.0,
    minimum_leave_one_family_out_RF_gain=0.0,
    column_scaled_relative_SVD_cutoff=1e-10,
    gaussian_prior_SD_sensitivity=[0.5, 1.0, 2.0],
    prior_sensitivity_changes_guard=False,
)


def _digest(values):
    return hashlib.sha256(json.dumps(values, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _basis(matrix):
    """Basis of the joint nuisance span, invariant to nonzero column units."""
    a = np.asarray(matrix, float)
    if a.ndim != 2 or not np.isfinite(a).all():
        raise ValueError("finite nuisance matrix required")
    lengths = np.linalg.norm(a, axis=0)
    use = lengths > 0
    if not use.any():
        return np.empty((len(a), 0)), np.empty(0)
    u, s, _ = np.linalg.svd(a[:, use] / lengths[use], full_matrices=False)
    rank = int(np.sum(s > POLICY["column_scaled_relative_SVD_cutoff"] * s[0]))
    return u[:, :rank], s


def project_support(values, control_mean, candidate_mean, control_nuisance,
                    candidate_nuisance, *, sigma_hz=150.0):
    """Exact common-span linear profile contrast for one observation subset.

    The union span allows nuisance at either endpoint to explain the same data.
    Hardware and orbit parameters are recalibrated using THIS subset only. The
    no-prior contrast has no covariance-volume or prior-penalty contribution.
    """
    y, m0, m1 = [np.asarray(v, float) for v in
                 (values, control_mean, candidate_mean)]
    if (y.ndim != 1 or y.shape != m0.shape or y.shape != m1.shape
            or not np.isfinite(np.r_[y, m0, m1]).all()
            or not np.isfinite(sigma_hz) or sigma_hz <= 0):
        raise ValueError("matching finite vectors and positive fixed noise required")
    a0, a1 = np.asarray(control_nuisance, float), np.asarray(candidate_nuisance, float)
    if a0.shape[0] != len(y) or a1.shape[0] != len(y):
        raise ValueError("nuisance rows must match observations")
    q, singular = _basis(np.column_stack((a0, a1)))

    def residual(v):
        return v - q @ (q.T @ v)

    raw_signature = (m1 - m0) / sigma_hz
    signature = residual(raw_signature)
    r0 = residual((y - m0) / sigma_hz)
    r1 = residual((y - m1) / sigma_hz)
    info = float(signature @ signature)
    # This algebra avoids cancellation between two large residual sums.
    gain = float(2 * r0 @ signature - info)
    raw_info = float(raw_signature @ raw_signature)
    rank = q.shape[1]
    return dict(
        points=len(y), nuisance_rank=rank, residual_dimension=len(y) - rank,
        displacement_information=info, projected_RF_gain=gain,
        control_profile_quadratic=float(r0 @ r0),
        candidate_profile_quadratic=float(r1 @ r1),
        unprojected_displacement_information=raw_info,
        retained_displacement_information_fraction=info / raw_info if raw_info > 0 else 0.0,
        nuisance_confounding_fraction=1 - info / raw_info if raw_info > 0 else None,
        scaled_nuisance_singular_values=singular.tolist(),
        empty_residual_space=rank == len(y),
        negligible_projected_displacement=bool(info < 1e-12),
    )


def gaussian_sensitivity(values, mean, nuisance, scale):
    """Normalized fixed-noise Gaussian diagnostic, jointly integrating nuisance.

    This uses nominal Gaussian engineering widths, not Gamma posterior means.
    It is a separate declared approximation when the inference phase prior has
    heavy tails. Its ranking never changes the projection guard decision.
    """
    raw = (np.asarray(values) - np.asarray(mean)) / POLICY["noise_sigma_hz"]
    a = np.asarray(nuisance) * scale / POLICY["noise_sigma_hz"]
    gram = np.eye(a.shape[1]) + a.T @ a
    root = np.linalg.cholesky(gram)
    b = np.linalg.solve(root.T, np.linalg.solve(root, a.T @ raw))
    innovation = raw - a @ b
    quadratic = float(innovation @ innovation + b @ b)
    logdet = float(2 * np.log(np.diag(root)).sum())
    noise_volume = 2 * len(raw) * np.log(POLICY["noise_sigma_hz"])
    return dict(negative_twice_log_density=float(quadratic + logdet + noise_volume
                + len(raw) * np.log(2 * np.pi)), quadratic=quadratic,
                nuisance_logdet=logdet,
                posterior_standardized_coefficient_norm=float(np.linalg.norm(b)))


def evaluate_arrays(values, control_mean, candidate_mean, control_nuisance,
                    candidate_nuisance, families, *, control_prior_design=None,
                    candidate_prior_design=None):
    """RF-only core, also usable with synthetic geometry without corpus I/O."""
    y, m0, m1, u0, u1 = [np.asarray(v, float) for v in
                         (values, control_mean, candidate_mean,
                          control_nuisance, candidate_nuisance)]
    family = np.asarray(families)
    if family.ndim != 1 or len(family) != len(y) or not len(y):
        raise ValueError("nonempty family labels matching observations required")
    all_families = np.unique(family)
    full = project_support(y, m0, m1, u0, u1)
    leave_out = []
    for excluded in all_families:
        use = family != excluded
        if not use.any():
            continue
        leave_out.append(dict(excluded_family=int(excluded),
            **project_support(y[use], m0[use], m1[use], u0[use], u1[use])))
    reasons = []
    if len(all_families) < POLICY["minimum_other_families"]:
        reasons.append("fewer_than_three_other_families")
    if full["displacement_information"] < POLICY["minimum_displacement_information"]:
        reasons.append("weak_other_family_displacement_information")
    if full["projected_RF_gain"] < POLICY["minimum_projected_RF_gain"]:
        reasons.append("insufficient_other_family_RF_support_for_displacement")
    if any(v["displacement_information"] < POLICY["minimum_leave_one_family_out_information"]
           for v in leave_out):
        reasons.append("weak_leave_one_family_out_displacement_information")
    if any(v["projected_RF_gain"] < POLICY["minimum_leave_one_family_out_RF_gain"]
           for v in leave_out):
        reasons.append("contradictory_leave_one_family_out_RF_support")
    sensitivity = []
    prior0 = u0 if control_prior_design is None else np.asarray(control_prior_design, float)
    prior1 = u1 if candidate_prior_design is None else np.asarray(candidate_prior_design, float)
    # Fragment constants already carry their .3 prior SD in the caller's design.
    for scale in POLICY["gaussian_prior_SD_sensitivity"]:
        c0 = gaussian_sensitivity(y, m0, prior0, scale)
        c1 = gaussian_sensitivity(y, m1, prior1, scale)
        sensitivity.append(dict(prior_SD_multiplier=scale, control=c0, candidate=c1,
            normalized_gaussian_gain=c0["negative_twice_log_density"]
                                     - c1["negative_twice_log_density"]))
    return dict(status="complete", guard_pass=not reasons, reasons=reasons,
                policy=dict(POLICY), other_families=list(map(int, all_families)),
                full=full, leave_one_family_out=leave_out,
                nominal_gaussian_prior_sensitivity=sensitivity)


def _endpoint(endpoint):
    for key in ("x", "x_km", "endpoint_east_north_km"):
        if key in endpoint:
            x = np.asarray(endpoint[key], float)
            if x.shape != (2,) or not np.isfinite(x).all():
                raise ValueError("finite east/north endpoint pair required")
            return x
    raise ValueError("endpoint lacks x, x_km, or endpoint_east_north_km")


def _inventory(p):
    ids, families = [], []
    for i, row, sl in zip(p.members, p.rows, p.slices, strict=True):
        native = p.scan.tracks[i]["observation_ids"]
        if len(native) != sl.stop - sl.start:
            raise ValueError("native IDs must follow original curved design")
        ids.extend(native)
        families.extend([int(row["candidate_norad"])] * len(native))
    if len(ids) != len(p.keep) or len(ids) != len(set(ids)):
        raise ValueError("unique native IDs matching the curved design required")
    return ids, np.asarray(families)


def _geometry(d, z, arm, x):
    from algo07_science import engine as e
    from dsx01_joint_marginal import JointMarginal

    reference = np.zeros(len(d["means"]))
    dd = dict(d, entries=[], families=[])
    zz = dict(z or {})
    zz.pop("selected", None)
    zz.pop("gap_selected", None)
    p, _ = e.build(dd, zz, arm, reference)
    # Use geometry only. The all-row Gaussian intermediate is discarded in full;
    # no observed CFO or fitted coefficient determines the returned mean/design.
    c = JointMarginal.calculate(p, x)
    u = c["features"]
    mean = np.zeros(u.shape[1])
    begin = p.hardware.shape[1] + p.smooth.shape[1]
    mean[begin:begin + len(p.labels)] = np.asarray(d["means"]) / p.phase_sigma
    nominal = p.q * c["intercept"] + u @ mean
    # The report's inherited fragment prior SD is .3, all other nominal
    # standardized coefficient SDs are one. This is ONLY a sensitivity design.
    prior_design = u.copy()
    prior_design[:, -len(p.members):] *= .3
    return p, nominal, u, prior_design, np.asarray(c["elevation"])


def evaluate_guard(base_context, candidate_context, control_endpoint,
                   candidate_endpoint, *, arm, target_family, z=None):
    """Evaluate saved endpoints against independently recalibrated other RF.

    Exactly the same eligible curved native IDs, CFO values, aliases, causal
    phase means and c arm are required. Target data are absent from every
    projection. Ancillary conditional and phase-mixture likelihoods are omitted
    and counted. The intervention must change only target-family covariance;
    changes to other-family nominal means are outside this diagnostic's scope.
    """
    if arm not in ("c0", "fitted_c"):
        raise ValueError("matched declared c arm required")
    if not np.array_equal(base_context["means"], candidate_context["means"]):
        raise ValueError("causal phase prior means changed")
    x0, x1 = _endpoint(control_endpoint), _endpoint(candidate_endpoint)
    p0, m0, u0, prior0, elevation0 = _geometry(base_context, z, arm, x0)
    p1, m1, u1, prior1, elevation1 = _geometry(candidate_context, z, arm, x1)
    ids0, family0 = _inventory(p0)
    ids1, family1 = _inventory(p1)
    if (ids0 != ids1 or not np.array_equal(family0, family1)
            or not np.array_equal(p0.keep, p1.keep)
            or not np.array_equal(p0.values, p1.values)
            or not np.array_equal(p0.q, p1.q)
            or list(p0.alias) != list(p1.alias)):
        raise ValueError("fixed curved observation contract changed")
    use = np.asarray(p0.keep, bool) & (family0 != int(target_family))
    if not use.any():
        return dict(status="no_other_family_evidence", guard_pass=False,
                    reasons=["no_other_family_evidence"], policy=dict(POLICY))
    result = evaluate_arrays(p0.values[use], m0[use], m1[use], u0[use], u1[use],
                             family0[use], control_prior_design=prior0[use],
                             candidate_prior_design=prior1[use])
    if np.any(elevation0[use] < 0) or np.any(elevation1[use] < 0):
        result["reasons"].append("other_family_nominal_prediction_below_horizon")
        result["guard_pass"] = False
    result.update(
        arm=arm, target_family=int(target_family),
        control_position_km=x0.tolist(), candidate_position_km=x1.tolist(),
        displacement_km=float(np.linalg.norm(x1 - x0)),
        other_native_ids_sha256=_digest([oid for oid, keep in zip(ids0, use) if keep]),
        eligible_native_ids_sha256=_digest([oid for oid, keep in zip(ids0, p0.keep) if keep]),
        other_points=int(use.sum()), excluded_target_points=int(np.sum(p0.keep & ~use)),
        excluded_ancillary_entries=len(base_context.get("entries", [])),
        excluded_ancillary_families=len(base_context.get("families", [])),
        zero_absolute_phase_reference=True, saved_phase_references_used=False,
        target_fitted_hardware_used=False, GPS_used=False,
        scope="curved-only RF, fixed native identities/masks/aliases and nominal physical support",
        limitations="Conservative shared-nuisance union may remove real position information. "
        "Fixed150 white-noise and nominal phase linearization are diagnostics, not calibrated "
        "uncertainty. Families can retain common unmodeled orbit/hardware errors. In-sample "
        "other-family support and family deletion robustness do not guarantee position accuracy "
        "or identity uniqueness. Abstention does not establish a bad association.",
    )
    return result
