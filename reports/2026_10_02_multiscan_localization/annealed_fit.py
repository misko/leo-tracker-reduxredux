"""Broad-to-narrow initialization with unchanged final coherent likelihood."""

from coherent_fit import FixedBankLikelihood, anchor_partition, frozen_identity_masses
from staged_fit import (
    candidate_ladder,
    fit_receiver_lines,
    frozen_row_weights,
    refine_bank,
    select_trials,
)
from track_likelihood import prepare_track_grouped_likelihood
from track_seed import fit_rough


def continue_banks(
    data, initial, ladder, prepared, anchors, *, share_predictions=False, optimizer="lbfgs"
):
    if optimizer == "lbfgs":
        refiner = refine_bank
        options = {"share_predictions": share_predictions}
    elif optimizer == "gauss-newton":
        from gauss_newton import refine_gauss_newton

        refiner = refine_gauss_newton
        options = {}
    else:
        raise ValueError("Unknown continuation optimizer")
    full_bank, full_support = ladder[-1]
    masses = frozen_identity_masses(anchors, full_bank, full_bank)
    parameters = initial.copy()
    warmup = []
    for sigma in (2000.0, 1000.0, 500.0):
        likelihood = FixedBankLikelihood(prepared, masses)
        trial = refiner(
            data,
            parameters,
            full_bank,
            full_support,
            likelihood,
            sigma_hz=sigma,
            budget_s=10.0,
            **options,
        )
        trial["sigma_hz"] = sigma
        warmup.append(trial)
        parameters = trial["parameters"].copy()
    trials = []
    for satellites, support in ladder:
        candidate_initial = parameters.copy()
        candidate_initial[6:] = 0
        candidate_initial[6 + satellites] = parameters[6 + satellites]
        candidate_masses = frozen_identity_masses(anchors, full_bank, satellites)
        likelihood = FixedBankLikelihood(prepared, candidate_masses)
        trial = refiner(
            data,
            candidate_initial,
            satellites,
            support,
            likelihood,
            sigma_hz=200.0,
            budget_s=45.0,
            **options,
        )
        trial.pop("satellite_weights")
        trial["sigma_hz"] = 200.0
        trial["identity_masses"] = candidate_masses
        trial["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(trial)
    return warmup, parameters, trials


def fit_annealed(data, rough=None, *, share_predictions=False, optimizer="lbfgs"):
    rough = fit_rough(data) if rough is None else rough
    initial = fit_receiver_lines(data, rough)
    capture_count = len(getattr(data, "child_sessions", [data.session_id]))
    anchors = anchor_partition(data, max_anchors=12 * capture_count)
    ladder = candidate_ladder(
        rough["assignments"], sizes=tuple(size * capture_count for size in (4, 8, 12))
    )
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in anchors],
    )
    warmup, warmed_parameters, trials = continue_banks(
        data,
        initial,
        ladder,
        prepared,
        anchors,
        share_predictions=share_predictions,
        optimizer=optimizer,
    )
    return {
        "rough": rough,
        "rx_initial": initial,
        "anchors": anchors,
        "full_bank": ladder[-1][0],
        "warmup": warmup,
        "warmed_parameters": warmed_parameters,
        "shared_predictions": bool(share_predictions or optimizer == "gauss-newton"),
        "optimizer": optimizer,
        "trials": trials,
        **select_trials(trials),
        "scope": "Coherent likelihood with a frozen 2000/1000/500 Hz initialization schedule "
        "on the largest proposed bank (10s per stage). Only final 200 Hz trials enter model "
        "selection (45s per bank). Priors and identity masses match coherent-v1. "
        "Data-dependent proposals and anchors make this a conditional likelihood proxy.",
    }
