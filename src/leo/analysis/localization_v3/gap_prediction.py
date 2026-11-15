"""Research-only timing-gap triage from the unchanged calibrated posterior.

The screen has no identity or inclusion authority. It retains a component if
either calibration arm admits any already accepted, active satellite family.
Absent usable shared calibration also retains the component for full checks.
"""

from copy import copy

import numpy as np
from scipy.linalg import cho_solve

from leo.analysis.localization_v3.gap_fragments import gap_context, prepare_gap
from leo.analysis.localization_v3.prediction import prediction_models
from leo.analysis.research.retained_track_likelihood import PERIOD

ARMS = ("c0", "fitted_c")
POLICY = dict(
    id="selective-timing-gap-prediction-experiment-v1",
    maximum_predictive_standard_deviations=5.0,
    distance="sqrt(alias-profiled residual.T @ predictive_covariance^-1 @ residual / points)",
    distance_is_calibrated_probability=False,
    retain_if="any accepted active family in either matched c arm is plausible",
    missing_shared_calibration="retain for independent checks",
    target_used_for_calibration=False,
    independent_identity_and_inclusion_required=True,
    GPS_used=False,
)


def predictive_distance(observed, mean, covariance):
    """Profile only the integer CFO alias under the fixed predictive Gaussian."""
    y, mu, cov = (np.asarray(v, float) for v in (observed, mean, covariance))
    if (y.ndim != 1 or not len(y) or mu.shape != y.shape
            or cov.shape != (len(y), len(y))
            or not all(np.isfinite(v).all() for v in (y, mu, cov))):
        raise ValueError("matching finite predictive observations, mean and covariance required")
    root = np.linalg.cholesky(cov)
    raw = y - mu
    unit = np.ones(len(y))
    weighted_unit = cho_solve((root, True), unit)
    optimum = -float(weighted_unit @ raw) / float(unit @ weighted_unit) / PERIOD
    aliases = {int(np.floor(optimum)), int(np.ceil(optimum))}
    rows = []
    for alias in sorted(aliases):
        residual = raw + alias * PERIOD
        quadratic = float(residual @ cho_solve((root, True), residual))
        distance = float(np.sqrt(max(0.0, quadratic) / len(y)))
        rows.append(dict(alias=alias, quadratic=quadratic,
                         predictive_standard_deviations=distance,
                         raw_RMS_hz=float(np.sqrt(np.mean(residual ** 2))),
                         mean_residual_hz=float(np.mean(residual))))
    return min(rows, key=lambda row: (row["quadratic"], abs(row["alias"]), row["alias"]))


def screen_timing_targets(context, inventory, observations, incumbent_owners, targets):
    """Return retained original targets and paired, radio-only triage evidence.

    This opt-in research policy does not replace direct-timing-gap-v1 selection.
    Callers must preserve the original independent branch qualification path.
    """
    if set(context["problems"]) != set(ARMS) or set(incumbent_owners) != set(ARMS):
        raise ValueError("matched calibration arms and incumbent ownership required")
    supported = {}
    for arm in ARMS:
        p, _ = context["problems"][arm]
        accepted = set(incumbent_owners[arm].values())
        supported[arm] = {
            row["candidate_index"]
            for row, sl in zip(p.rows, p.slices, strict=True)
            if p.keep[sl].any() and int(context["scan"].norads[row["candidate_index"]]) in accepted
        }
    shared = sorted(supported["c0"] & supported["fitted_c"])
    rows, retained = [], []
    for target in targets:
        row = dict(track_id=target["track_id"], branch_id=target["branch_id"],
                   predictions=[], retained=True, reason="no shared active calibration")
        if shared:
            source = prepare_gap(context, inventory, observations, target["track_id"])
            d, entry = gap_context(context, inventory, source, target["branch_id"], observations)
            track = d["scan"].tracks[entry["track_index"]]
            for j in shared:
                paired = {}
                for arm in ARMS:
                    original, x = context["problems"][arm]
                    p = copy(original)
                    p.scan = d["scan"]
                    means, covs, logprior, phases, elevations, prior = prediction_models(
                        d, p, x, entry["track_index"], j)
                    if (prior["kind"] != "existing_shared_posterior"
                            or not prior["active_curved_family"]):
                        raise ValueError("screen requires an unchanged active-family posterior")
                    if means.shape[0] != 1 or len(phases) != 1:
                        raise ValueError("screen requires the existing calibrated phase posterior")
                    if not np.isfinite(logprior[0]):
                        paired[arm] = dict(usable=False, reason="posterior family below horizon")
                        continue
                    paired[arm] = dict(usable=True, phase_s=float(phases[0]),
                                       minimum_elevation_deg=float(elevations[0]),
                                       **predictive_distance(track["values"], means[0], covs[0]))
                row["predictions"].append(dict(candidate_index=j,
                    norad=int(context["scan"].norads[j]), arms=paired))
            usable = [value for prediction in row["predictions"]
                      for value in prediction["arms"].values() if value["usable"]]
            if usable:
                row["retained"] = any(value["predictive_standard_deviations"] <=
                    POLICY["maximum_predictive_standard_deviations"] for value in usable)
                row["reason"] = ("plausible accepted-family prediction" if row["retained"]
                                 else "all accepted-family predictions distant")
            else:
                row["reason"] = "no observable shared active calibration"
        rows.append(row)
        if row["retained"]:
            retained.append(target)
    return dict(policy=dict(POLICY), targets=retained, rows=rows,
                no_GPS_inference=True, causal_only=True)
