"""Joint predictive family geometry and physical diagnostics, owned by v3."""

import copy
import json

import numpy as np
from scipy.linalg import block_diag, cho_solve
from scipy.optimize import minimize

from leo.analysis.localization_v3 import numerical_policy as numerics
from leo.analysis.localization_v3.event_position import cached, make_event_problem, summary
from leo.analysis.localization_v3.joint_density import two_family_phase_evidence
from leo.analysis.localization_v3.new_family import NewFamily
from leo.analysis.localization_v3.predictive_linear import geometry_features, linear_geometry
from leo.analysis.localization_v3.recovery_acceptance import owner_changes
from leo.analysis.localization_v3.recovery_gates import exact_gate_replay
from leo.analysis.localization_v3.recovery_inclusion import (
    attach_recovery_predictive as attach_event_predictive,
)
from leo.analysis.localization_v3.recovery_inventory import memberships
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.predictive_track import (
    condition_coefficients,
    phase_mixture_evidence,
    phase_resolution_agreement,
    receiver_design,
)
from leo.analysis.research.retained_track_likelihood import PERIOD, profile


def joint_density(d, *inputs):
    policy = d.get("numerical_policy")
    if policy is None:
        return two_family_phase_evidence(*inputs)
    return two_family_phase_evidence(
        *inputs, optimize_contractions=policy.joint_contraction_optimized
    )


def joint_inputs(families, p, x, powers, old_entries):
    c = p.curved_calculate(x) if old_entries else p.calculate(x)
    coef = c["coefficient"]
    u = c["features"][p.keep]
    groups = p.noise_groups[p.keep]
    w = np.asarray(powers)[groups] * c["noise_precision"][groups] / p.point_noise[p.keep] ** 2
    gram = np.diag(c["coefficient_prior_precision"]) + u.T @ (u * w[:, None])
    cov = cho_solve((np.linalg.cholesky(gram), True), np.eye(len(gram)))
    mean = coef
    posterior = cov
    if old_entries:
        view, y, sigma, g, _ = linear_geometry(p, old_entries)
        geo = geometry_features(view, x, 0.0)
        h = geo["features"]
        noise = np.diag(2 * sigma * sigma) + 300.0**2 * (g[:, None] == g[None, :])
        mean, posterior = condition_coefficients(
            coef, cov, h, y - view.q * geo["intercept"] - h @ coef, noise
        )
    designs = []
    means = []
    modes = []
    visible = []
    for family in families:
        if family.j in p.labels and any(
            (
                r["candidate_index"] == family.j and p.keep[sl].any()
                for r, sl in zip(p.rows, p.slices, strict=True)
            )
        ):
            raise ValueError("family already has active calibration data")
        if any(e["candidate_index"] == family.j for e in old_entries):
            raise ValueError("family already has predictive data")
        receiver = np.concatenate(
            [
                receiver_design(
                    t["times"],
                    t["rf_hz"],
                    t["receiver"],
                    t["channel"],
                    family.scan.rx_basis[e["track_index"]],
                    fitted_c=p.fitted_c,
                )
                for t, e in zip(family.tracks, family.entries, strict=True)
            ]
        )
        h = np.zeros((len(family.times), len(coef)))
        h[:, : receiver.shape[1]] = receiver
        designs.append(h)
        f, e, uu = family.geometry(*p.scan.search_region.latlon(x))
        means.append(h @ mean + f.reshape(len(family.phases), -1) * family.q)
        modes.append(uu.reshape(len(family.phases), len(family.times), 3) * family.q[None, :, None])
        visible.append(e.reshape(len(family.phases), -1).min(axis=1) >= 0)
    h = np.concatenate(designs)
    base = block_diag(*(f.noise for f in families)) + h @ posterior @ h.T
    return (
        [f.values for f in families],
        means,
        base,
        modes,
        [f.logprior for f in families],
        visible,
    )


def evidence(families, p, x, d, method):
    inputs = joint_inputs(families, p, x, d["powers"], d["entries"])
    if method == "joint":
        return joint_density(d, *inputs)["negative_twice_log_density"]
    y, means, covariance, modes, priors, visible = inputs
    n = len(y[0])
    return sum(
        (
            phase_mixture_evidence(
                y[k], means[k], covariance[sl, sl], modes[k], priors[k], visible[k]
            )["negative_twice_log_density"]
            for k, sl in enumerate((slice(0, n), slice(n, len(covariance))))
        )
    )


def at_phases(families, phases):
    result = []
    for family, phase in zip(families, phases, strict=True):
        f = copy.copy(family)
        f.phases = np.array([phase])
        f.grid_times = f.times
        f.grid_labels = np.zeros(len(f.times), int)
        f.logprior = np.zeros(1)
        f.bank = {k: v if k == "time_s" else v[:1] for k, v in family.bank.items()}
        f.modes = {k: v if k == "time_s" else v[:3] for k, v in family.modes.items()}
        result.append(f)
    return result


def joint_diagnostics(families, p, x, d, refine=False):
    full = joint_density(d, *joint_inputs(families, p, x, d["powers"], d["entries"]))
    phases = np.array(
        [f.phases[k] for f, k in zip(families, full["joint_map_indices"], strict=True)]
    )
    refine_success = None
    if refine:

        def score(z):
            fs = at_phases(families, z)
            r = joint_density(d, *joint_inputs(fs, p, x, d["powers"], d["entries"]))
            return r["negative_twice_log_density"] - 2 * sum(
                (f.distribution.logpdf(v) for f, v in zip(families, z, strict=True))
            )

        widths = [f.phases[1] - f.phases[0] for f in families]
        opt = minimize(
            score,
            phases,
            method="Powell",
            bounds=[
                (max(-15.0, v - w), min(15.0, v + w)) for v, w in zip(phases, widths, strict=True)
            ],
            options=dict(maxiter=40, maxfev=240, xtol=1e-07, ftol=1e-10),
        )
        phases = opt.x
        refine_success = bool(opt.success)
    fs = at_phases(families, phases)
    point = joint_density(d, *joint_inputs(fs, p, x, d["powers"], d["entries"]))
    c = p.curved_calculate(x) if d["entries"] else p.calculate(x)
    coefficient = c["coefficient"].copy()
    gates, diagnostics = ([], [])
    for f, orbit in zip(fs, point["orbital_map_mean"], strict=True):
        freq, elevation = paired_phase_frequency(
            f.bank, f.grid_times, f.grid_labels, f.phases, *p.scan.search_region.latlon(x)
        )
        modes = paired_frequency_modes(
            f.bank, f.modes, f.grid_times, f.grid_labels, f.phases, *p.scan.search_region.latlon(x)
        )
        receiver = np.concatenate(
            [
                receiver_design(
                    t["times"],
                    t["rf_hz"],
                    t["receiver"],
                    t["channel"],
                    f.scan.rx_basis[e["track_index"]],
                    fitted_c=p.fitted_c,
                )
                for t, e in zip(f.tracks, f.entries, strict=True)
            ]
        )
        prediction = receiver @ coefficient[: receiver.shape[1]] + f.q * (freq + modes @ orbit)
        raw = f.values - prediction
        for entry, track, sl in zip(f.entries, f.tracks, f.slices, strict=True):
            terms = profile(
                raw[sl],
                np.zeros(sl.stop - sl.start),
                *f.scan.white[entry["track_index"]],
                bias_sigma=300.0,
            )
            screen = batch_noise_screen(terms["innovations"], track["times"])
            valid = bool(
                terms["rms"][0] <= 450
                and abs(terms["bias"][0]) <= 3000
                and (int(terms["alias"][0]) == 0)
                and screen["noise_screen_pass"][0]
                and (elevation[sl].min() >= 0)
            )
            gates.append(dict(component=entry["component"], norad=entry["norad"], compatible=valid))
            diagnostics.append(
                dict(
                    component=entry["component"],
                    norad=entry["norad"],
                    times_s=track["times"],
                    CFO_hz=track["values"],
                    prediction_CFO_hz=prediction[sl] - entry["alias"] * PERIOD,
                    raw_residual_hz=raw[sl],
                    profile_bias_hz=float(terms["bias"][0]),
                    profile_RMS_hz=float(terms["rms"][0]),
                    minimum_elevation_deg=float(elevation[sl].min()),
                    noise={
                        k: bool(v[0]) if v.dtype == bool else float(v[0]) for k, v in screen.items()
                    },
                )
            )
    after = p.curved_calculate(x) if d["entries"] else p.calculate(x)
    return dict(
        gates=gates,
        diagnostics=diagnostics,
        phases_s=phases,
        refined=refine,
        refinement_success=refine_success,
        receiver_calibration_change=float(np.max(abs(coefficient - after["coefficient"]))),
        phase_boundary_mass=[
            float(w[abs(f.phases) >= 14.9].sum())
            for f, w in zip(families, full["phase_marginals"], strict=True)
        ],
    )


def scoped_membership(before, after, target, fitted, owners_before, owners_after):
    before, after, target, fitted = map(set, (before, after, target, fitted))
    if before & target:
        raise ValueError("target already belongs to control")
    if not before <= after or not target <= after:
        raise ValueError("lost incumbent or missing target")
    if any((owners_after.get(o) != n for o, n in owners_before.items())):
        raise ValueError("incumbent owner changed")
    incidental = after - before - target
    if incidental & fitted:
        raise ValueError("incidental extension entered the fitted observations")
    return dict(
        reviewed_associated_ids=sorted(before | target),
        incidental_unvalidated_ids=sorted(incidental),
        added_validated_target_ids=sorted(target),
        raw_proposed_count=len(after),
        reviewed_proposed_count=len(before | target),
    )


def probe_joint(d, inclusions, phase_step=0.0625):
    """Verify independent additions before sharing their receiver uncertainty."""
    if len(inclusions) != 2:
        raise ValueError("two individually qualified families required")
    targets = []
    for inclusion in inclusions:
        trial, audit = inclusion["trial"], inclusion["audit"]
        if not (
            trial["control"]["paired_valid"]
            and trial["new_family"]["paired_valid"]
            and audit["all_verified"]
        ):
            raise ValueError("individually qualified native trials required")
        protocol = trial["protocol"]
        if any(
            protocol.get(k)
            for k in (
                "inactive_fragment_sources",
                "graph_bundle_sources",
                "measurement_refinements",
            )
        ):
            raise ValueError("native unchanged trials required")
        if inclusion["annotation"]["status"] != "conditionally_supported_identity":
            raise ValueError("supported causal identities required")
        targets.append(protocol["targets"])
    if len({e["candidate_index"] for group in targets for e in group}) != 2:
        raise ValueError("distinct families required")
    ids = [o for group in targets for e in group for o in e["observation_ids"]]
    if len(ids) != len(set(ids)):
        raise ValueError("overlapping target observations")
    families = [
        NewFamily(
            d["scan"], group, d["model"], phase_step=phase_step, allow_uncalibrated_label=True
        )
        for group in targets
    ]
    offsets = np.array([[0, 0], [0.1, 0], [-0.1, 0], [0, 0.1], [0, -0.1]])
    protocol = dict(
        targets=targets,
        phase_step_s=phase_step,
        offsets_km=offsets,
        position_source="saved RF incumbent per c arm; no GPS initialization",
        frozen_phase_reference=True,
        positions_refitted=False,
        causal_only=True,
        receiver_covariance_integrated_once=True,
        no_production_change=True,
    )
    rows, centers = [], {}
    for arm, (p, x) in d["problems"].items():
        centers[arm] = np.asarray(x)
        before = (p.curved_calculate(x) if d["entries"] else p.calculate(x))["coefficient"].copy()
        for offset in offsets:
            z = np.asarray(x) + offset
            if np.max(abs(z)) > 12.5:
                raise ValueError("local probe leaves regional box")
            inputs = joint_inputs(families, p, z, d["powers"], d["entries"])
            joint = joint_density(d, *inputs)
            y, m, b, u, lp, v = inputs
            n1, individual = len(y[0]), []
            for k, sl in enumerate((slice(0, n1), slice(n1, len(b)))):
                score = phase_mixture_evidence(y[k], m[k], b[sl, sl], u[k], lp[k], v[k])[
                    "negative_twice_log_density"
                ]
                replay = families[k].evaluate(p, z, d["powers"], d["entries"])
                if abs(score - replay) > 1e-6:
                    raise ValueError("individual-family likelihood replay failed")
                individual.append(score)
            l1, l2 = np.linalg.cholesky(b[:n1, :n1]), np.linalg.cholesky(b[n1:, n1:])
            cross = np.linalg.solve(l2, np.linalg.solve(l1, b[:n1, n1:]).T).T
            rows.append(
                dict(
                    arm=arm,
                    offset_km=offset,
                    position_east_north_km=z,
                    joint_score=joint["negative_twice_log_density"],
                    factorized_score=sum(individual),
                    individual_scores=individual,
                    joint_minus_factorized=joint["negative_twice_log_density"] - sum(individual),
                    largest_cross_correlation=float(np.linalg.svd(cross, compute_uv=False)[0]),
                    phase_marginals=joint["phase_marginals"],
                    joint_map_phases_s=[
                        float(f.phases[k])
                        for f, k in zip(families, joint["joint_map_indices"], strict=True)
                    ],
                    phase_boundary_mass=[
                        float(w[abs(f.phases) >= 14.9].sum())
                        for f, w in zip(families, joint["phase_marginals"], strict=True)
                    ],
                    orbital_map_mean=joint["orbital_map_mean"],
                    phase_pair_count=joint["phase_pair_count"],
                )
            )
        after = (p.curved_calculate(x) if d["entries"] else p.calculate(x))["coefficient"]
        np.testing.assert_array_equal(before, after)
    gradients = {}
    for arm in centers:
        group = [r for r in rows if r["arm"] == arm]
        gradients[arm] = {
            key: [(group[1][key] - group[2][key]) / 0.2, (group[3][key] - group[4][key]) / 0.2]
            for key in ("joint_score", "factorized_score")
        }
    return dict(
        protocol=protocol,
        result=dict(
            rows=rows,
            gradients_per_km=gradients,
            centers=centers,
            all_individual_replays_verified=True,
            receiver_calibration_unchanged=True,
            position_inclusion_authorized=False,
        ),
    )


def fit_joint(d, probe, arm, method, *, optimizer="lbfgsb"):
    if arm not in ("c0", "fitted_c") or method not in ("control", "factorized", "joint"):
        raise ValueError("known method and calibration arm required")
    if optimizer not in ("lbfgsb", "powell"):
        raise ValueError("known matched optimizer required")
    receipt = probe["result"]
    if not (
        receipt["all_individual_replays_verified"] and receipt["receiver_calibration_unchanged"]
    ):
        raise ValueError("verified joint input probe required")
    targets, step = probe["protocol"]["targets"], probe["protocol"]["phase_step_s"]
    protocol = dict(
        targets=targets,
        method=method,
        arm=arm,
        phase_step_s=step,
        start_east_north_km=[0, 0],
        box_width_km=25,
        phase_rounds=5,
        maxiter=48,
        GPS_used=False,
        future_TLE=False,
        diagnostic_only=True,
        association_authorized=False,
    )
    if optimizer == "lbfgsb":
        protocol["maxfun"] = 240
        result = _fit_lbfgsb(d, targets, arm, method, step)
    else:
        protocol.update(optimizer="Powell", maxfev=240, numerical_only_selection=True)
        result = _fit_powell(d, targets, arm, method, step)
    return dict(protocol=protocol, result=result)


def joint_numerical_only(experiments):
    """Every factorized, joint and control audit must support numerical retry."""
    records = [
        experiments[method][arm]
        for method in ("control", "factorized", "joint")
        for arm in ("c0", "fitted_c")
    ]
    return bool(
        any(not r["trial"]["result"]["history"][-1]["success"] for r in records)
        and all(
            not r["audit"]["incumbent_owner_changes"]
            and r["audit"]["phase_check"]["phase_change_s"] <= 0.01
            and all(v["all_pass"] for v in r["audit"]["exact_incumbent_orbits"])
            and all(v for k, v in r["audit"]["checks"].items() if k != "incumbent_and_numerical")
            for r in records
        )
    )


def _fit_lbfgsb(d, targets, arm, method, phase_step):
    families = [
        NewFamily(
            d["scan"], group, d["model"], phase_step=phase_step, allow_uncalibrated_label=True
        )
        for group in targets
    ]
    x = np.zeros(2)
    reference = np.zeros(len(d["means"]))
    history = []
    for _iteration in range(5):
        kw = {"base_problem_factory": d["problem_factory"]} if "problem_factory" in d else {}
        p = make_event_problem(
            d["scan"],
            d["node"],
            d["keep"],
            arm,
            reference,
            d["powers"],
            d["means"],
            d["model"],
            [],
            **kw,
        )
        numerics.check_problem(d, p)
        attach_event_predictive(p, d["entries"], d["powers"])
        cached(p)

        def objective(z, p=p):
            c = p.calculate(z)
            penalty = float(np.sum(np.minimum(0, c["elevation"][p.keep]) ** 2) / 4)
            addition = 0.0 if method == "control" else evidence(families, p, z, d, method)
            return c["negative_twice_elbo"] + penalty + addition

        opt = numerics.minimize(
            d,
            minimize,
            objective,
            x,
            method="L-BFGS-B",
            bounds=[(-12.5, 12.5)] * 2,
            options=dict(maxiter=48, maxfun=240, eps=0.001, ftol=1e-10, gtol=0.0001, maxls=20),
        )
        x = np.asarray(opt.x)
        reference, check = numerics.refresh(d, p, p.state(x)["phases"][p.labels], reference)
        row = dict(
            endpoint_east_north_km=x,
            objective=float(opt.fun),
            success=bool(opt.success),
            message=str(opt.message),
            nfev=opt.nfev,
            **check,
        )
        history.append(row)
    result = summary(p, x, d["entries"])
    result["history"] = history
    result["method"] = method
    result["arm"] = arm
    result["incumbent_objective"] = result["negative_twice_elbo"]
    result["joint_evidence"] = evidence(families, p, x, d, "joint")
    result["factorized_evidence"] = evidence(families, p, x, d, "factorized")
    if method != "control":
        result["negative_twice_elbo"] += result[method + "_evidence"]
    result["joint_phase_result"] = joint_density(
        d, *joint_inputs(families, p, x, d["powers"], d["entries"])
    )
    result["joint_phase_grid_s"] = [f.phases for f in families]
    result["association_authorized"] = False
    result["pending_checks"] = [
        "joint target physical residuals",
        "exact incumbent orbit replay",
        "membership and ownership",
        "local phase quadrature agreement",
    ]
    return result


def _fit_powell(d, targets, arm, method, phase_step):
    families = [
        NewFamily(
            d["scan"], group, d["model"], phase_step=phase_step, allow_uncalibrated_label=True
        )
        for group in targets
    ]
    x = np.zeros(2)
    reference = np.zeros(len(d["means"]))
    history = []
    for _iteration in range(5):
        kw = {"base_problem_factory": d["problem_factory"]} if "problem_factory" in d else {}
        p = make_event_problem(
            d["scan"],
            d["node"],
            d["keep"],
            arm,
            reference,
            d["powers"],
            d["means"],
            d["model"],
            [],
            **kw,
        )
        numerics.check_problem(d, p)
        attach_event_predictive(p, d["entries"], d["powers"])
        cached(p)

        def objective(z, p=p):
            c = p.calculate(z)
            penalty = float(np.sum(np.minimum(0, c["elevation"][p.keep]) ** 2) / 4)
            return (
                c["negative_twice_elbo"]
                + penalty
                + (0.0 if method == "control" else evidence(families, p, z, d, method))
            )

        opt = numerics.minimize(
            d,
            minimize,
            objective,
            x,
            method="Powell",
            bounds=[(-12.5, 12.5)] * 2,
            options=dict(maxiter=48, maxfev=240, ftol=1e-10, xtol=1e-05),
        )
        x = np.asarray(opt.x)
        reference, check = numerics.refresh(d, p, p.state(x)["phases"][p.labels], reference)
        row = dict(
            endpoint_east_north_km=x,
            objective=float(opt.fun),
            success=bool(opt.success),
            message=str(opt.message),
            nfev=opt.nfev,
            **check,
        )
        history.append(row)
    result = summary(p, x, d["entries"])
    result.update(
        history=history,
        method=method,
        arm=arm,
        optimizer="Powell",
        incumbent_objective=result["negative_twice_elbo"],
    )
    for score_method in ("joint", "factorized"):
        result[score_method + "_evidence"] = evidence(families, p, x, d, score_method)
    if method != "control":
        result["negative_twice_elbo"] += result[method + "_evidence"]
    result.update(
        joint_phase_result=joint_density(
            d, *joint_inputs(families, p, x, d["powers"], d["entries"])
        ),
        joint_phase_grid_s=[f.phases for f in families],
        association_authorized=False,
        pending_checks=["physical replay", "ownership", "phase resolution"],
    )
    return result


class QuadratureExecutionFailure(BaseException):
    """Incomplete parallel audit work cannot become a scientific rejection."""


def _quadrature_scores(families, problem, position, context, method, offsets, mapper=None):
    """Preserve every offset/grid value using at most three ordered process batches.

    Only joint evidence is expensive enough to batch. Unknown policy/factory
    hooks retain the serial path. Grid evaluation must not change policy receipts.
    """
    policy = context.get("numerical_policy")
    if (mapper is None or method != "joint" or "problem_factory" in context
            or (policy is not None and type(policy) is not numerics.NumericalPolicy)):
        return np.array([[evidence(f, problem, position + offset, context, method)
                          for f in families] for offset in offsets])
    def receipt():
        return json.dumps(policy.receipt, sort_keys=True, allow_nan=False) if policy else None
    before = receipt()
    width = max(1, (len(offsets) + 2) // 3)
    batches = [tuple(range(start, min(start + width, len(offsets))))
               for start in range(0, len(offsets), width)]
    def evaluate(indices):
        values = [[evidence(f, problem, position + offsets[i], context, method)
                   for f in families] for i in indices]
        return indices, values, receipt()
    completed = list(mapper(evaluate, batches))
    if len(completed) != len(batches) or receipt() != before:
        raise QuadratureExecutionFailure("Incomplete grid batches or modified parent policy")
    rows = []
    for expected, item in zip(batches, completed, strict=True):
        if not isinstance(item, tuple) or len(item) != 3:
            raise QuadratureExecutionFailure("Malformed grid batch result")
        indices, values, state = item
        if (not isinstance(indices, tuple) or indices != expected or state != before
                or not isinstance(values, list) or len(values) != len(expected)
                or any(not isinstance(row, list) or len(row) != len(families) for row in values)):
            raise QuadratureExecutionFailure("Grid order, shape or numerical policy changed")
        rows.extend(values)
    return np.array(rows)


def audit_joint(d, inv, trial, control_audit=None, *, map_batches=None):
    pr, saved = (trial["protocol"], trial["result"])
    arm = pr["arm"]
    p0, x0 = d["problems"][arm]
    _, _, old_ids, old_owners = memberships(p0, x0, d["entries"])
    if old_ids != set(inv["policy"][arm]["proposed_associated_ids"]):
        raise ValueError("incumbent membership replay failed")
    kw = {"base_problem_factory": d["problem_factory"]} if "problem_factory" in d else {}
    p = make_event_problem(
        d["scan"],
        d["node"],
        d["keep"],
        arm,
        np.array(saved["phase_reference"]),
        d["powers"],
        d["means"],
        d["model"],
        [],
        **kw,
    )
    numerics.check_problem(d, p)
    attach_event_predictive(p, d["entries"], d["powers"])
    cached(p)
    x = np.array(saved["endpoint_east_north_km"])
    families = [
        NewFamily(
            d["scan"],
            group,
            d["model"],
            phase_step=pr["phase_step_s"],
            allow_uncalibrated_label=True,
        )
        for group in pr["targets"]
    ]
    _, _, ids, owners = memberships(p, x, d["entries"])
    objective = p.calculate(x)["negative_twice_elbo"]
    target_ids = {o for group in pr["targets"] for e in group for o in e["observation_ids"]}
    fitted = {
        o
        for i, sl in zip(p.members, p.slices, strict=True)
        for o, k in zip(d["scan"].tracks[i]["observation_ids"], d["keep"][sl], strict=True)
        if k
    }
    fitted.update(o for e in d["entries"] for o in e["observation_ids"])
    target = refined = quadrature = scope = None
    if pr["method"] != "control":
        objective += evidence(families, p, x, d, pr["method"])
        if target_ids & ids:
            raise ValueError("target duplicates retained evidence")
        ids.update(target_ids)
        for group in pr["targets"]:
            for e in group:
                owners.update({o: e["norad"] for o in e["observation_ids"]})
        fitted.update(target_ids)
        control = control_audit
        scope = scoped_membership(
            control["reviewed_ids"], ids, target_ids, fitted, control["owners"], owners
        )
        if pr["method"] == "joint":
            target = joint_diagnostics(families, p, x, d)
            refined = joint_diagnostics(families, p, x, d, refine=True)
        else:
            target = [f.evaluate(p, x, d["powers"], d["entries"], details=True) for f in families]
            refined = [
                f.evaluate(p, x, d["powers"], d["entries"], details=True, refine_phase=True)
                for f in families
            ]
        offsets = np.array([[0, 0], [0.025, 0], [-0.025, 0], [0, 0.025], [0, -0.025]])
        if np.max(abs(x)) + 0.025 > 12.5:
            quadrature = dict(local_agreement=False, reason="boundary")
        else:
            steps = [pr["phase_step_s"] / k for k in (1, 2, 4)]
            fs = [
                [
                    NewFamily(
                        d["scan"], group, d["model"], phase_step=step, allow_uncalibrated_label=True
                    )
                    for group in pr["targets"]
                ]
                for step in steps
            ]
            scores = _quadrature_scores(fs, p, x, d, pr["method"], offsets, map_batches)
            quadrature = dict(
                steps_s=steps,
                offsets_km=offsets,
                scores=scores,
                **phase_resolution_agreement(scores),
            )
    difference = float(objective - saved["negative_twice_elbo"])
    if abs(difference) > 1e-05:
        raise ValueError("objective replay failed")
    labels = {
        r["candidate_index"] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()
    }
    labels.update(e["candidate_index"] for e in d["entries"])
    exact = []
    for j in sorted(labels):
        p.explicit_phase_family = j
        exact.append(dict(norad=int(p.scan.norads[j]), **exact_gate_replay(p, x, d["entries"])))
    _, phase = numerics.refresh(d, p, p.state(x)["phases"][p.labels], p.reference)
    changed = owner_changes(old_owners, owners)
    base_pass = bool(
        not changed
        and old_ids <= ids
        and all(r["all_pass"] for r in exact)
        and (phase["phase_change_s"] <= 0.01)
        and saved["history"][-1]["success"]
    )
    checks = dict(incumbent_and_numerical=base_pass)
    if target is not None:
        details = [target, refined] if pr["method"] == "joint" else target + refined
        checks.update(
            target_gates=all(g["compatible"] for z in details for g in z["gates"]),
            receiver_unchanged=all(z["receiver_calibration_change"] == 0 for z in details),
            phase_resolution=quadrature["local_agreement"],
            phase_interior=all(np.max(z["phase_boundary_mass"]) < 0.01 for z in details),
            continuous_phase_completed=refined["refinement_success"]
            if pr["method"] == "joint"
            else True,
        )
    reviewed = scope["reviewed_associated_ids"] if scope else sorted(old_ids)
    reviewed_owners = {o: owners[o] for o in reviewed}
    return dict(
        method=pr["method"],
        arm=arm,
        checks=checks,
        RF_qualified_arm=all(checks.values()),
        joint_pair_requires_both_arms=True,
        objective_difference=difference,
        target=target,
        continuous_target=refined,
        quadrature=quadrature,
        scope=scope,
        exact_incumbent_orbits=exact,
        incumbent_owner_changes=changed,
        phase_check=phase,
        reviewed_ids=reviewed,
        owners=reviewed_owners,
        production_changed=False,
    )
