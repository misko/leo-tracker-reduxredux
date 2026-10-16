"""DS21-039 fixed-alpha factory and explicitly labelled composite fit receipts."""

import numpy as np

from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.research import cross_band_consistency
from leo.analysis.research.likelihood_tempering import LikelihoodTemperedObjective

POLICY = dict(
    schema="ds21-039-likelihood-tempering-v2",
    amendment="Rename statistical prior ledger to preserve delegated RegionalPrior fitter port",
    arm="fitted-c",
    alphas=[1.0, 0.25],
    objective="alpha*original marginalized observation NLL + original priors once",
    prior="Original common/relative/group penalties and bounds unchanged",
    interpretation="Prespecified regularization sensitivity; not noise/covariance/effectiveN",
    probabilities="Unchanged original fixed-state latent posteriors",
    predictive_score="Original untempered normalized native likelihood",
    oracle_tolerance=1e-7,
    temporal_edges=0,
    waveform="Original neutral evidence",
)


def build_tempered_model(case, alpha):
    if alpha not in POLICY["alphas"] or isinstance(alpha, bool):
        raise ValueError("Only prespecified alpha=1 or alpha=.25 supported")
    model = LikelihoodTemperedObjective(case["model"], alpha)
    if model.base.branches.waveform_measured.any():
        raise ValueError("Original neutral waveform DS21 control required")
    return model, dict(
        **POLICY,
        alpha=model.alpha,
        windows=len(model.observations.window_ids),
        native_candidates=len(model.base.native_rows),
        group_receivers=list(model.frame.receivers),
        high_fractions=list(model.frame.high_fractions),
        time_center_s=model.observations.time_center_s,
        rf_center_hz=model.observations.rf_center_hz,
        parameter_count=model.size,
        nuisance_count=len(model.initial_nuisance),
        common_sigma_s=model.score.common_sigma_s,
        relative_sigma_s=model.score.relative_sigma_s,
        group_sigma_hz=model.sigma_hz,
    )


def replay_alpha1(model, vector, nuisance, *, fit=None, guard=lambda: None):
    if model.alpha != 1:
        raise ValueError("Source oracle requires actual alpha=1 model")
    guard()
    old = model.original_model.evaluate_joint(vector, nuisance)
    new = model.evaluate_joint(vector, nuisance)
    deltas = dict(
        objective=float(new[0] - old[0]),
        likelihood_nll=float(new[3].nll - old[3].nll),
        vector_gradient=float(np.max(abs(new[1] - old[1]), initial=0)),
        nuisance_gradient=float(np.max(abs(new[2] - old[2]), initial=0)),
        satellite_posterior=float(
            np.max(abs(new[3].responsibilities - old[3].responsibilities), initial=0)
        ),
        clutter_posterior=float(
            np.max(abs(new[3].clutter_probability - old[3].clutter_probability), initial=0)
        ),
        residual=float(np.max(abs(new[3].residual_hz - old[3].residual_hz), initial=0)),
        prediction_gradient=float(
            np.max(abs(new[3].prediction_gradient - old[3].prediction_gradient), initial=0)
        ),
    )
    if fit is not None:
        deltas.update(
            saved_objective=float(old[0] - fit["objective"]),
            saved_likelihood_nll=float(old[3].nll - fit["likelihood_nll"]),
        )
    return dict(
        passed=all(
            np.isfinite(x) and abs(x) <= POLICY["oracle_tolerance"] for x in deltas.values()
        ),
        deltas=deltas,
    )


def fit_tempered_calibration(model, vector, nuisance, **kwargs):
    if kwargs.get("arm", "fitted-c") != "fitted-c":
        raise ValueError("Likelihood scale control fits common c only")
    fit = dict(fit_group_calibration(model, vector, nuisance, **kwargs))
    if "vector" in fit:
        fit.update(
            likelihood_alpha=model.alpha,
            likelihood_kind="Scaled composite training cost",
            scaled_likelihood_nll=fit["likelihood_nll"],
            untempered_likelihood_nll=fit["likelihood_nll"] / model.alpha,
            normalized_predictive_nll=False,
            original_conditional_posteriors=True,
        )
    return fit


def native_residual_rms(audit):
    """Condition native branch mass before products, retaining ambiguity spread."""
    posterior = audit.posterior
    maximum = float(np.max(posterior, initial=0))
    if maximum == 0:
        return None
    weights = posterior / maximum
    return float(np.sqrt(np.sum(weights * audit.residual_hz**2) / weights.sum()))


def diagnose_tempered_state(model, vector, nuisance, *, guard=lambda: None):
    guard()
    value, gradient, extra, terms = model.evaluate_joint(vector, nuisance)
    ledger, _, _ = model.prior_ledger(vector, nuisance)
    np.testing.assert_allclose(value, terms.nll + ledger["total"], atol=1e-8, rtol=1e-12)
    mass = float(terms.responsibilities.sum())
    base = model.base
    prediction, visible, _, _ = predict_orbits(
        base.bank,
        base.native_observations,
        base.prior,
        np.asarray(vector)[:2],
        vector[7] + base.basis @ np.asarray(vector)[8:],
    )
    prediction += (
        base.native_design @ np.asarray(vector)[2:7]
        + base.baseline[base.native_rows]
        + (model.group_design @ np.asarray(nuisance))[base.native_rows]
    )[:, None]
    guard()
    audit = cross_band_consistency.native_history_residuals(
        base.native_observations.measured_hz,
        prediction,
        visible,
        base.native_rows,
        base.native_slots,
        base.branches.available,
        base.branches.waveform_log_evidence,
        base.families,
        base.initial,
        sigma_hz=base.score.sigma_hz,
        sample_rate_hz=base.sample_rate_hz,
        signal_stay=base.signal_stay,
        clutter_stay=base.clutter_stay,
    )
    np.testing.assert_allclose(audit.nll, terms.nll / model.alpha, atol=1e-8, rtol=1e-11)
    posterior = np.zeros_like(terms.responsibilities)
    np.add.at(posterior, base.native_rows, audit.posterior)
    np.testing.assert_allclose(posterior, terms.responsibilities, atol=1e-12, rtol=1e-10)
    np.testing.assert_allclose(
        audit.clutter_probability, terms.clutter_probability, atol=1e-12, rtol=1e-10
    )
    return dict(
        alpha=model.alpha,
        objective=float(value),
        scaled_likelihood_nll=float(terms.nll),
        untempered_likelihood_nll=float(terms.nll / model.alpha),
        prior_costs=ledger,
        gradient=gradient.tolist(),
        nuisance_gradient=extra.tolist(),
        signal_mass=mass,
        clutter_mass=float(terms.clutter_probability.sum()),
        conditional_mean_residual_rms_hz=float(
            np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)
        )
        if mass > 0
        else None,
        posterior_native_rms_hz=native_residual_rms(audit),
        likelihood_is_normalized_predictive=False,
        limitation=POLICY["interpretation"],
    )
