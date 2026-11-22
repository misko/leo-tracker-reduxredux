"""Evaluate the full discovery cost and retain diagnostics only for each nominee."""

from contextlib import contextmanager
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import discovery
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import BIAS, NOISE, PERIOD, profile


def winner_rms(residual, column_order):
    """Keep the stock axis reduction order for a Fortran-layout candidate matrix."""
    squares = residual**2
    if column_order:
        columns = np.zeros((2, len(squares)), order="F")
        columns[0] = squares
        return float(np.sqrt(columns.mean(axis=1)[0]))
    return float(np.sqrt(squares.mean()))


def white_nomination(observed, predicted, visible, whitening):
    """Retain stock alias and white profile arithmetic at every catalogue row."""
    inverse, logvolume = whitening
    one = np.diag(inverse)
    if np.count_nonzero(inverse) != len(observed) or np.count_nonzero(one) != len(observed):
        terms = profile(observed, predicted, inverse, logvolume)
        j = int(np.argmin(np.where(visible, terms["cost"], np.inf)))
        return j, terms["cost"], terms["alias"], terms["bias"][j], terms["rms"][j], (
            terms["innovations"][j]
        )
    # The operations and layout of these reductions follow profile(). Only
    # the selected row needs an unweighted residual and a retained innovation.
    raw = observed - predicted
    alias = np.rint(-raw.mean(axis=1) / PERIOD)
    raw += alias[:, None] * PERIOD
    z = raw * one
    information = one @ one
    bias = z @ one / (information + 1 / BIAS**2)
    energy = z - bias[:, None] * one
    np.square(energy, out=energy)
    cost = np.sum(energy, axis=1) + (bias / BIAS) ** 2
    cost += logvolume + np.log1p(BIAS**2 * information)
    j = int(np.argmin(np.where(visible, cost, np.inf)))
    innovation = NOISE * (z[j] - bias[j] * one)
    rms = winner_rms(raw[j] - bias[j], raw.flags.f_contiguous and not raw.flags.c_contiguous)
    return j, cost, alias, bias[j], rms, innovation


@contextmanager
def streamed_nomination(scan, counters):
    """Bind only the two discovery routes that consume ungated nominations."""
    association = scan.association
    original_rows = discovery.nomination_rows
    streamed = object()

    def select(current, rows, nominations):
        if current is scan and nominations is streamed:
            return rows
        return original_rows(current, rows, nominations)

    def associate(state, base, point, method, *, all_tracks=False):
        if all_tracks or state["extra"] or method not in ("shared_phase", "receiver_smooth"):
            return association(state, base, point, method, all_tracks=all_tracks)
        projected = scan.predictions(state, base, point, method)
        frequency, elevation, _ = projected
        rows = []
        for i in scan.curved:
            track, indexes = scan.tracks[i], scan.index[i]
            rf = track["rf_hz"] / discovery.REFERENCE_RF
            observed = track["values"] - scan.hardware(track, state["beta"])
            if method == "receiver_smooth":
                observed -= rf * scan.rx_basis[i] @ state["smooth"][track["receiver"] - 1]
            visible = elevation[:, indexes].min(axis=1) >= 0
            j, cost, _, bias, rms, innovation = white_nomination(
                observed, rf * frequency[:, indexes], visible, scan.white[i]
            )
            passing = rms <= 450 and abs(bias) <= 3000 and bool(
                batch_noise_screen(innovation[None, :], track["times"])["noise_screen_pass"][0]
            )
            rows.append(dict(component=track["key"], candidate_index=j,
                             candidate_norad=int(scan.norads[j]), points=len(observed),
                             compatible=passing, active_curvature=True, rms_hz=float(rms),
                             bias_hz=float(bias), cost=float(cost[j]), parts=1, split_at=-1,
                             times_s=track["times"]))
            counters["profiles"] += 1
            counters["candidate_rows"] += len(frequency)
            counters["avoided_residual_rows"] += len(frequency) - 1
        # Both discovery callers consume select() on these pairs. The complete
        # association routine remains in use everywhere outside this scope.
        return None, rows, streamed, projected

    with (
        patch.object(scan, "association", associate),
        patch.object(discovery, "nomination_rows", select),
    ):
        yield
