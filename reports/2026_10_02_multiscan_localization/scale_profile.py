"""Select a GLRT residual width using normalized likelihood, never reference error."""

import numpy as np
from coherent_fit import FixedBankLikelihood
from gauss_newton import refine_gauss_newton
from staged_fit import frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


def fit_scale_profile(data, source, initial, *, widths=(100, 200, 400, 800), budget_s=10):
    widths = np.asarray(widths, dtype=float)
    if widths.ndim != 1 or not len(widths) or np.any(~np.isfinite(widths)) or np.any(widths <= 0):
        raise ValueError("Widths must be a nonempty positive finite vector")
    if len(np.unique(widths)) != len(widths):
        raise ValueError("Widths must be unique")
    initial = np.asarray(initial, dtype=float)
    prepared = prepare_track_grouped_likelihood(
        data.measured, data.group, row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in source["anchors"]],
    )
    scale_penalty = 0.5 * np.log(len(np.unique(data.group)))
    trials = []
    for incumbent in source["trials"]:
        satellites = np.asarray(incumbent["satellite_indices"], dtype=int)
        for width in widths:
            seed = initial.copy()
            seed[6:] = 0
            seed[6 + satellites] = initial[6 + satellites]
            likelihood = FixedBankLikelihood(prepared, incumbent["identity_masses"])
            trial = refine_gauss_newton(
                data, seed, satellites, np.ones(len(satellites)), likelihood,
                sigma_hz=float(width), budget_s=budget_s,
            )
            trial.pop("satellite_weights", None)
            trial["sigma_hz"] = float(width)
            trial["scale_selection_penalty"] = float(scale_penalty)
            trial["selection_score"] += float(scale_penalty)
            trial["identity_masses"] = incumbent["identity_masses"]
            trials.append(trial)
    return {
        "trials": trials, **select_trials(trials), "widths_hz": widths,
        "scope": "All widths use normalized wrapped Gaussian density, identical observations, "
        "frozen bank masses and the same initialization. Selection uses negative log likelihood "
        "plus timing prior, satellite entry penalty and one residual-scale parameter penalty. "
        "Conditional development proxy, not calibrated evidence or held-out validation.",
    }
