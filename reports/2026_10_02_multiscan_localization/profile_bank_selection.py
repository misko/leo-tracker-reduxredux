"""Reevaluate frozen candidate banks from a truth-free profile-search seed."""

import copy

import numpy as np
from coherent_fit import FixedBankLikelihood
from gauss_newton import refine_gauss_newton
from staged_fit import frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


def refine_profile_banks(data, source, zoom, budget_s=20):
    parameters = np.asarray(zoom["selected"]["fit"]["parameters"], dtype=float)
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in source["anchors"]],
    )
    trials = []
    attempts = []
    for incumbent in source["trials"]:
        satellites = np.asarray(incumbent["satellite_indices"], dtype=int)
        initial = parameters.copy()
        initial[6:] = 0
        initial[6 + satellites] = parameters[6 + satellites]
        likelihood = FixedBankLikelihood(prepared, incumbent["identity_masses"])
        candidate = refine_gauss_newton(
            data, initial, satellites, np.ones(len(satellites)), likelihood,
            sigma_hz=200, budget_s=budget_s,
        )
        candidate.pop("satellite_weights", None)
        candidate["identity_masses"] = copy.deepcopy(incumbent["identity_masses"])
        candidate["likelihood_diagnostics"] = {
            key: value for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        attempts.append(candidate)
        winner = min([incumbent, candidate], key=lambda trial: trial["selection_score"])
        trials.append(copy.deepcopy(winner))
    return {
        "attempts": attempts,
        "trials": trials,
        **select_trials(trials),
        "bank_selection_reevaluated": True,
        "scope": "Frozen candidate banks, anchors, identity masses and penalties. "
        "Each bank branches from the same profile seed with omitted timing offsets zeroed. "
        "Original incumbents are retained if their penalized objective is lower.",
    }
