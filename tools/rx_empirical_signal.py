"""Signal-plus-empirical-background relative likelihood kernel."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.special import logsumexp

FloatArray = NDArray[np.float64]


def _log_expit(value: FloatArray) -> FloatArray:
    return -np.logaddexp(0.0, -value)


def paired_relative_log_likelihood(
    log_count_probabilities: ArrayLike,
    signal_ratios: ArrayLike,
    counts: ArrayLike,
    logits: ArrayLike,
    visibility: ArrayLike,
    *,
    latent_sd: float = 1.0,
    quadrature_order: int = 5,
) -> FloatArray:
    """Integrate the signal/background likelihood ratio over shared RX state.

    ``log_count_probabilities[..., s0, s1]`` contains the background log PMF
    at counts ``(n0 - s0, n1 - s1)``.  It may have shape ``(W, 2, 2)`` or
    ``(W, C, 2, 2)``.  ``signal_ratios[..., r]`` is ``sum_j g(x_j)/f(x_j)``;
    the latent signal assignment contributes this sum divided by ``n_r``.
    """
    ratios = np.asarray(signal_ratios, dtype=float)
    count_array = np.asarray(counts)
    linear = np.asarray(logits, dtype=float)
    visible = np.asarray(visibility, dtype=bool)
    count_logs = np.asarray(log_count_probabilities, dtype=float)
    if ratios.ndim != 3 or ratios.shape[-1] != 2:
        raise ValueError("signal_ratios must have shape (windows, components, 2)")
    windows, components, _ = ratios.shape
    if linear.shape != ratios.shape:
        raise ValueError("logits must have the same shape as signal_ratios")
    if count_array.shape != (windows, 2):
        raise ValueError("counts must have shape (windows, 2)")
    if visible.shape != (windows, components):
        raise ValueError("visibility must have shape (windows, components)")
    if count_logs.shape == (windows, 2, 2):
        count_logs = np.broadcast_to(count_logs[:, None], (windows, components, 2, 2))
    elif count_logs.shape != (windows, components, 2, 2):
        raise ValueError("log_count_probabilities must end in a 2 by 2 signal-pattern grid")
    if np.any(ratios < 0) or not np.all(np.isfinite(ratios)):
        raise ValueError("signal_ratios must be finite and nonnegative")
    if (
        not np.all(np.isfinite(count_array))
        or np.any(count_array < 0)
        or not np.all(count_array == np.floor(count_array))
    ):
        raise ValueError("counts must be nonnegative integers")
    if not np.all(np.isfinite(linear)):
        raise ValueError("logits must be finite")
    if np.any(np.isnan(count_logs)) or np.any(np.isposinf(count_logs)):
        raise ValueError("count log probabilities may contain only finite values or -infinity")
    if np.any(~np.isfinite(count_logs[..., 0, 0])):
        raise ValueError("observed background count probability must be finite")
    if not np.isfinite(latent_sd) or latent_sd < 0:
        raise ValueError("latent_sd must be finite and nonnegative")
    if (
        isinstance(quadrature_order, bool)
        or int(quadrature_order) != quadrature_order
        or quadrature_order < 1
    ):
        raise ValueError("quadrature_order must be a positive integer")

    log_assignment = np.full_like(ratios, -np.inf)
    possible = (count_array[:, None, :] > 0) & (ratios > 0)
    broadcast_counts = np.broadcast_to(count_array[:, None, :], ratios.shape)
    log_assignment[possible] = np.log(ratios[possible]) - np.log(broadcast_counts[possible])
    log_count_ratio = count_logs - count_logs[..., :1, :1]
    nodes, weights = np.polynomial.hermite.hermgauss(int(quadrature_order))
    latent = np.sqrt(2.0) * latent_sd * nodes
    log_weights = np.log(weights) - 0.5 * np.log(np.pi)
    by_node = np.empty((len(nodes), windows, components), dtype=float)
    for node_index, offset in enumerate(latent):
        shifted = linear + offset
        log_p = _log_expit(shifted)
        log_not_p = _log_expit(-shifted)
        patterns = []
        for signal0 in (0, 1):
            for signal1 in (0, 1):
                value = log_count_ratio[..., signal0, signal1].copy()
                value += log_p[..., 0] if signal0 else log_not_p[..., 0]
                value += log_p[..., 1] if signal1 else log_not_p[..., 1]
                if signal0:
                    value += log_assignment[..., 0]
                if signal1:
                    value += log_assignment[..., 1]
                patterns.append(value)
        by_node[node_index] = logsumexp(np.stack(patterns), axis=0)
    integrated = logsumexp(by_node + log_weights[:, None, None], axis=0)
    return np.where(visible, integrated, 0.0)
