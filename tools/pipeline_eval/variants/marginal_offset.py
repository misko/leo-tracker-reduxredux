"""Integrate one source-scaled constant native-Hz discrepancy per owned Graph track."""

from dataclasses import replace
from unittest.mock import patch

import numpy as np

from . import joint_clock_model as fixed
from . import joint_orbits as joint
from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "marginal_offset"
STOCK = "marginal_offset_zero"
BOUNDARY = "Native Graph through matched fixed-owner position and whole-track predictive scoring"
# Frozen v5 analysis/research/retained_track_likelihood.py applies this prior
# in native Hertz once per merged carrier component. Here one Graph track is
# the unit, and the receiver's existing correlated noise remains in force.
SIGMA_HZ = 1000.0


class ConstantPrior:
    def __init__(self, base, length, sigma_hz):
        self.base = base
        one = base @ np.ones(length)
        information = float(one @ one)
        self.direction = one / np.sqrt(information)
        self.log_volume = float(np.log1p(sigma_hz**2 * information))
        self.shrink = -np.expm1(-0.5 * self.log_volume)
        self.gain = (sigma_hz**2 / (1 + sigma_hz**2 * information)) * one

    def __matmul__(self, value):
        z = self.base @ value
        if z.ndim == 1:
            return z - self.shrink * self.direction * (self.direction @ z)
        return z - self.shrink * self.direction[:, None] * (self.direction @ z)

    def posterior(self, value):
        return float(self.gain @ (self.base @ value))


def _profile_rows(rows, sigma_hz):
    if sigma_hz == 0:
        return rows
    result = []
    for row in rows:
        arc, tr = row.arc, row.arc.track
        white = ConstantPrior(tr.whiten, len(tr.t), sigma_hz)
        result.append(replace(row, arc=replace(arc, track=replace(tr, whiten=white))))
    return result


def _radio(track, state):
    return (
        state.bias[track.lane]
        + state.drift[track.lane] * track.drift
        + (track.rf / 1e9 - 11.5) * state.c_hz_per_ghz
    )


def _loss(rows, tile, region, state):
    site = region.site(state.xy)[0]
    raw_square = score = 0.0
    points = 0
    for row in rows:
        track = row.arc.track
        phase = state.phase[row.orbit]
        frequency = exact.project(tile, row.orbit, track.t, site, phase, track.rf)[0]
        raw = track.hz - frequency - _radio(track, state) - row.alias * lean.PERIOD
        innovation = track.whiten @ raw
        raw_square += float(raw @ raw)
        weight = min(1, 40 / len(raw)) / (1 + row.loss / 4)
        score += weight * float(innovation @ innovation)
        points += len(raw)
    prior = np.r_[
        state.xy / 1000,
        state.bias / (lean.PERIOD / np.sqrt(12)),
        state.drift / 1500,
        state.c_hz_per_ghz / 200000,
        state.phase / lean.PHASE_SD_S,
    ]
    return score + float(prior @ prior), float(np.sqrt(raw_square / points))


def refine(rows, start, tile, region, half, arm, sigma_hz):
    profiled = _profile_rows(rows, sigma_hz)
    state, radius = start.state, start.radius_km
    score, rms = _loss(profiled, tile, region, state)
    accepted = 0
    for _ in range(exact.RELINEARIZATIONS):
        proposal = lean.fit(
            exact._recenter(profiled, tile, region, state), len(tile.positions_km), half, arm
        )
        if proposal is None:
            break
        radius = proposal.radius_km
        for fraction in exact.BACKTRACK:
            update = exact._blend(state, proposal.state, fraction)
            loss, error = _loss(profiled, tile, region, update)
            if loss + 1e-8 < score:
                state, score, rms = update, loss, error
                accepted += 1
                break
        else:
            break
    # For a fixed owner set and scale the determinant is constant throughout
    # backtracking. Add it to the reported objective after optimization.
    volume = sum(
        fixed._scale(row) ** 2 * getattr(row.arc.track.whiten, "log_volume", 0.0)
        for row in profiled
    )
    return lean.Fit(state, rms, score + volume, radius), dict(accepted_steps=accepted)


def held_score(rows, state, sigma_hz):
    """Score whole held tracks under the Gaussian prior with fixed owners and aliases."""
    losses, supported, raw_square, points = [], set(), 0.0, 0
    for row in _profile_rows(rows, sigma_hz):
        arc, j, track = row.arc, row.winner, row.arc.track
        phase = state.phase[row.orbit]
        raw = arc.residual[j] - arc.xy[j] @ state.xy - _radio(track, state)
        raw -= phase * arc.phase[j] + row.alias * lean.PERIOD
        residual = track.whiten @ raw
        volume = getattr(track.whiten, "log_volume", 0.0)
        loss = (float(residual @ residual) + volume + (phase / lean.PHASE_SD_S) ** 2) / len(raw)
        losses.append(loss)
        points += len(raw)
        raw_square += float(raw @ raw)
        if loss <= joint.OUTLIER_CEILINGS[-1]:
            supported.add(row.orbit)
    return dict(
        held_score=float(np.mean(1 / (1 + np.asarray(losses)))),
        held_normalized_mean_loss=float(np.mean(losses)),
        held_orbits=len(supported),
        held_compatible_tracks=int(
            np.count_nonzero(np.asarray(losses) <= joint.OUTLIER_CEILINGS[-1])
        ),
        held_raw_rms_hz=float(np.sqrt(raw_square / points)),
    )


def infer(document, offer, catalogue, *, sigma_hz):
    """Share the stock joint selection, followed by matched fit/gate evaluations."""
    original_solve, original_train = joint.solve, joint._train
    measurements = {}

    def solve(arcs, tile, region, half):
        training, held_rows = [], []

        def remember(selected, initial, n, size):
            answer = original_train(selected, initial, n, size)
            if not training:
                training.extend(answer[1])
                measurements["training_ownership"] = fixed._ownership(training)
            return answer

        def validate(held, state):
            arm = "c0" if not held_rows else "fitted_c"
            if not held_rows:
                held_rows.extend(lean.assign(held, state, update_phase=False))
                measurements["held_ownership"] = fixed._ownership(held_rows)
            start = lean.Fit(state, 0.0, 0.0, 0.0)
            current, details = refine(training, start, tile, region, half, arm, sigma_hz)
            score = held_score(held_rows, current.state, sigma_hz)
            measurements[f"held_{arm}"] = score | details
            return score

        def final(rows, start, tile, region, half, arm):
            measurements[f"final_{arm}_ownership"] = fixed._ownership(rows)
            result, details = refine(rows, start, tile, region, half, arm, sigma_hz)
            measurements[f"final_{arm}"] = details
            return result, details

        with (
            patch.object(joint, "_train", remember),
            patch.object(joint, "_validation", validate),
            patch.object(exact, "refine", final),
        ):
            return original_solve(arcs, tile, region, half)

    with patch.object(joint, "solve", solve):
        result = joint.infer(document, offer, catalogue)
    result["boundary"] = BOUNDARY
    result["metrics"].update(offset_sigma_hz=sigma_hz, offset_study=measurements)
    return result
