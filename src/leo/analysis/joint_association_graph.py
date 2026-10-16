"""Sparse satellite/absolute-CFO-branch/clutter histories for private research.

The graph is a sticky state with a clutter hub. Every row of its transition
matrix is normalized; changing satellite or CFO branch requires passage through
clutter. Reset families are fixed from metadata, never from fitted frequencies.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AssociationHistories:
    nll: float
    posterior: np.ndarray
    family_count: int
    transition_count: int


def continuity_families(times_s, family_keys, *, maximum_gap_s):
    """Return independent sorted sequences, resetting at gaps and metadata keys.

    Keys must include receiver, channel and retune/dwell identity. Sorting is
    internal only; the posterior is returned in the original observation order.
    """
    times = np.asarray(times_s, float)
    if (
        times.ndim != 1
        or len(family_keys) != len(times)
        or not np.isfinite(times).all()
        or not np.isfinite(maximum_gap_s)
        or maximum_gap_s <= 0
    ):
        raise ValueError("finite times, fixed aligned metadata and positive gap required")
    grouped = {}
    for index, key in enumerate(family_keys):
        grouped.setdefault(key, []).append(index)
    result = []
    for indices in grouped.values():
        indices = sorted(indices, key=lambda i: (times[i], i))
        current = []
        for index in indices:
            if current and times[index] - times[current[-1]] > maximum_gap_s:
                result.append(tuple(current))
                current = []
            # Coincident/overlapping top-one windows cannot be chained as
            # independent repeated evidence without a separate observation model.
            if current and times[index] <= times[current[-1]]:
                result.append(tuple(current))
                current = []
            current.append(index)
        if current:
            result.append(tuple(current))
    return tuple(result)


def sparse_forward_backward(
    log_emissions,
    families,
    initial,
    *,
    signal_stay=0.95,
    clutter_stay=0.5,
):
    """Marginalize normalized sparse histories in O(windows * states).

    State zero is clutter; all remaining states are satellite/branch pairs.
    Initial is a normalized physical prior. The clutter hub enters the signal
    states in proportion to that prior conditional on signal. Missing waveform
    data must use neutral emissions, never fabricated measured qualification.
    """
    emission = np.asarray(log_emissions, float)
    prior = np.asarray(initial, float)
    if (
        emission.ndim != 2
        or emission.shape[1] < 2
        or prior.shape != (emission.shape[1],)
        or np.isnan(emission).any()
        or np.isposinf(emission).any()
        or not np.isfinite(prior).all()
        or np.any(prior < 0)
        or not np.isclose(prior.sum(), 1)
        or not 0 < prior[0] < 1
        or not 0 < signal_stay < 1
        or not 0 < clutter_stay < 1
    ):
        raise ValueError("invalid normalized sparse association graph")
    inventory = [index for family in families for index in family]
    if sorted(inventory) != list(range(len(emission))) or any(not f for f in families):
        raise ValueError("families must partition the observation inventory exactly")
    entering = prior[1:] / (1 - prior[0])

    def forward(probability):
        value = np.empty_like(probability)
        value[0] = probability[0] * clutter_stay + probability[1:].sum() * (1 - signal_stay)
        value[1:] = probability[1:] * signal_stay
        value[1:] += probability[0] * (1 - clutter_stay) * entering
        return value

    def backward(value):
        result = np.empty_like(value)
        result[0] = clutter_stay * value[0] + (1 - clutter_stay) * (entering @ value[1:])
        result[1:] = signal_stay * value[1:] + (1 - signal_stay) * value[0]
        return result

    posterior = np.zeros_like(emission)
    nll = 0.0
    transitions = 0
    singleton = [family[0] for family in families if len(family) == 1]
    if singleton:
        rows = emission[singleton]
        scale = np.max(rows, axis=1)
        if not np.isfinite(scale).all():
            raise ValueError("every window requires at least one supported state")
        unnormalized = np.exp(rows - scale[:, None]) * prior
        norms = unnormalized.sum(axis=1)
        if np.any(norms <= 0):
            raise ValueError("graph has no supported path")
        posterior[singleton] = unnormalized / norms[:, None]
        nll -= float(np.sum(scale + np.log(norms)))
    for family in families:
        if len(family) == 1:
            continue
        rows = emission[list(family)]
        scale = np.max(rows, axis=1)
        if not np.isfinite(scale).all():
            raise ValueError("every window requires at least one supported state")
        likelihood = np.exp(rows - scale[:, None])
        alpha = np.empty_like(rows)
        norms = np.empty(len(rows))
        probability = prior
        for i in range(len(rows)):
            if i:
                probability = forward(alpha[i - 1])
            unnormalized = probability * likelihood[i]
            norms[i] = unnormalized.sum()
            if norms[i] <= 0:
                raise ValueError("graph has no supported path")
            alpha[i] = unnormalized / norms[i]
        nll -= float(np.sum(scale + np.log(norms)))
        beta = np.ones(emission.shape[1])
        for i in range(len(rows) - 1, -1, -1):
            joint = alpha[i] * beta
            posterior[family[i]] = joint / joint.sum()
            if i:
                beta = backward(likelihood[i] * beta) / norms[i]
        transitions += len(family) - 1
    return AssociationHistories(nll, posterior, len(families), transitions)
