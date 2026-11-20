"""Same-owner native position fits with a shared clock and marginal track offset."""

from dataclasses import dataclass, replace
from time import perf_counter
from unittest.mock import patch

import numpy as np
from scipy.linalg import cholesky, solve_triangular

from . import joint_clock_model as fit
from . import joint_orbits as joint
from . import marginal_offset as offset
from . import robust_em as lean
from . import robust_orbit_fit as exact

MODES = {
    "native_clock_offset_ou": (True, offset.SIGMA_HZ, True),
    "native_clock_offset_diag": (True, offset.SIGMA_HZ, False),
    "native_clock_only_ou": (True, 0.0, True),
    "native_offset_only_ou": (False, offset.SIGMA_HZ, True),
}
METHOD = next(iter(MODES))
BOUNDARY = "Complete native Graph through anonymous joint owners and marginal clock/offset fit"
GEO_GATES = {"weak_position_geometry", "position_at_tile_boundary", None}


class Diagonal:
    def __matmul__(self, array):
        return array / lean.WHITE_HZ


@dataclass(frozen=True)
class Whitening:
    base: object
    scale: float = 1.0

    def __matmul__(self, array):
        return self.scale * (self.base @ array)

    def __rmul__(self, value):
        return Whitening(self.base, value * self.scale)

    def posterior(self, value):
        return self.base.posterior(value)


def _profile(rows, sigma, ou):
    profiled = []
    volume = 0.0
    for row in rows:
        arc, track = row.arc, row.arc.track
        base = track.whiten if ou else Diagonal()
        logdet = (
            -2 * np.log(np.diag(base)).sum() if ou else 2 * len(track.t) * np.log(lean.WHITE_HZ)
        )
        white = offset.ConstantPrior(base, len(track.t), sigma) if sigma else base
        volume += fit._scale(row) ** 2 * (logdet + getattr(white, "log_volume", 0.0))
        if not isinstance(white, np.ndarray):
            white = Whitening(white)
        profiled.append(replace(row, arc=replace(arc, track=replace(track, whiten=white))))
    return profiled, float(volume)


def _residual(row, tile, site, state):
    track = row.arc.track
    frequency = exact.project(tile, row.orbit, track.t, site, state.phase[row.orbit], track.rf)[0]
    return track.hz - frequency - fit._radio(track, state) - row.alias * lean.PERIOD


def _solve(rows, start, tile, region, half, arm, mode, *, final=False):
    clock, sigma, ou = mode
    profiled, volume = _profile(rows, sigma, ou)
    current, info = fit.refine(profiled, start, tile, region, half, arm, clock=clock)
    info["weighted_noise_log_determinant"] = volume
    if final:
        site = region.site(current.state.xy)[0]
        square = n = 0
        for row in profiled:
            white = row.arc.track.whiten
            raw = _residual(row, tile, site, current.state)
            conditional = raw - white.posterior(raw) if sigma else raw
            square += float(conditional @ conditional)
            n += len(raw)
        info["fit_conditional_rf_rms_hz"] = float(np.sqrt(square / n))
    return replace(current, score=current.score + volume), info


def conditional(times, residual, prefix, sigma, ou):
    """Score p(suffix | prefix) with the integrated constant and optional OU state."""
    n = len(times)
    cov = np.full((n, n), sigma**2)
    if ou:
        lag = np.abs(times[:, None] - times)
        cov += lean.CORRELATED_HZ**2 * np.exp(-lag / lean.CORRELATION_S)
    cov.flat[:: n + 1] += lean.WHITE_HZ**2
    lower = cholesky(cov, lower=True)
    innov = solve_triangular(lower, residual, lower=True)[prefix:]
    tail = lower[prefix:, prefix:]
    raw = tail @ innov
    deviance = innov @ innov + 2 * np.log(np.diag(tail)).sum() + len(raw) * np.log(2 * np.pi)
    return float(raw @ raw), float(deviance), len(raw)


@dataclass(frozen=True)
class Held:
    assignment: lean.Assignment
    prefix: int


def _held_rows(arcs, tile, state):
    held = []
    for arc in arcs:
        track = arc.track
        n = 2 * len(track.t) // 3
        if n < 4:
            continue
        prefix = replace(
            track, t=track.t[:n], hz=track.hz[:n], drift=track.drift[:n],
            whiten=track.whiten[:n, :n],
        )
        shortlist = lean.shortlist(tile, prefix)
        if shortlist is not None:
            (chosen,) = lean.assign([shortlist], state, update_phase=False)
            complete = replace(shortlist, track=track)
            held.append(Held(replace(chosen, arc=complete), n))
    return held


def _held(held, train, start, tile, region, half, arm, mode):
    if not held:
        return {}
    current, _ = _solve(train, start, tile, region, half, arm, mode)
    site = region.site(current.state.xy)[0]
    square = deviance = raw_square = points = 0
    for item in held:
        row, prefix = item.assignment, item.prefix
        raw = _residual(row, tile, site, current.state)
        e, d, n = conditional(row.arc.track.t, raw, prefix, mode[1], mode[2])
        square += e
        deviance += d
        raw_square += float(raw[prefix:] @ raw[prefix:])
        points += n
    return dict(
        held_tracks=len(held), held_points=points,
        raw_held_rf_rms_hz=float(np.sqrt(raw_square / points)),
        conditional_held_rf_rms_hz=float(np.sqrt(square / points)),
        held_deviance_per_point=deviance / points,
    )


def _output(result, solutions, region, half, training_center):
    if len(solutions) != len(lean.ARMS):
        return dict(result)
    shift = float(np.linalg.norm(solutions["c0"].state.xy - training_center))
    reason = result["reason"]
    if reason in GEO_GATES:
        if shift > 4 or any(s.radius_km > 6 for s in solutions.values()):
            reason = "weak_position_geometry"
        elif any(np.max(np.abs(s.state.xy)) >= half - 0.75 for s in solutions.values()):
            reason = "position_at_tile_boundary"
        else:
            reason = None
    arms = {}
    for arm, solution in solutions.items():
        point = region.site(solution.state.xy)[1]
        arms[arm] = dict(
            result["arms"][arm], latlon=point if reason is None else None, forced_latlon=point,
            region_id=None if reason else region.name, forced_region_id=region.name,
            rf_rms_hz=solution.rms_hz, frequency_score=solution.score,
            c_hz_per_ghz=solution.state.c_hz_per_ghz, radius_km=solution.radius_km,
        )
    return dict(
        result, status="ok" if reason is None else "withheld", reason=reason, arms=arms,
        metrics=dict(result["metrics"], pooled_shift_km=shift),
    )


def compare(document, offer, catalogue, methods=tuple(MODES)):
    """Share the untouched joint selection and original publication predictions."""
    primary = methods[0]
    native_solve, native_train, native_validate = joint.solve, joint._train, joint._validation
    native = {}
    fitted = {name: {} for name in methods}
    details = {name: {} for name in methods}
    times = {name: 0.0 for name in methods}

    def solve(arcs, tile, region, half):
        native.update(tile=tile, region=region, half=half)

        def select(*args):
            out = native_train(*args)
            if "train" not in native:
                native["train"], native["training_state"] = out[1], out[0]
            return out

        def validate(held, state):
            if "held" not in native:
                native["held"] = _held_rows(held, tile, state)
                native["held_starts"] = {"c0": state}
            else:
                native["held_starts"]["fitted_c"] = state
            return native_validate(held, state)

        def finalize(rows, start, tile, region, half, arm):
            receipt = fit._ownership(rows)
            previous = native.setdefault("final_digest", receipt)
            if receipt != previous:
                raise ValueError("calibration arms selected different native tracks or aliases")
            for name in methods:
                began = perf_counter()
                model, info = _solve(rows, start, tile, region, half, arm, MODES[name], final=True)
                times[name] += perf_counter() - began
                fitted[name][arm], details[name][arm] = model, info
            return fitted[primary][arm], details[primary][arm]

        with (
            patch.object(joint, "_train", select), patch.object(joint, "_validation", validate),
            patch.object(exact, "refine", finalize),
        ):
            return native_solve(arcs, tile, region, half)

    with patch.object(joint, "solve", solve):
        result = joint.infer(document, offer, catalogue)
    output, began = {}, perf_counter()
    for name in methods:
        selected = _output(
            result, fitted[name], native.get("region"), native.get("half"),
            native["training_state"].xy if native.get("training_state") is not None else None,
        )
        held = {}
        for arm, state in native.get("held_starts", {}).items():
            start = lean.Fit(state, 0.0, 0.0, 0.0)
            held[arm] = _held(
                native["held"], native["train"], start, native["tile"], native["region"],
                native["half"], arm, MODES[name],
            )
        selected["boundary"] = BOUNDARY
        selected["metrics"] = dict(
            selected["metrics"], final_ownership=native.get("final_digest"),
            training_ownership=fit._ownership(native.get("train", [])),
            held_prefix_ownership=fit._ownership(
                [item.assignment for item in native.get("held", [])]
            ),
            conditional_held_by_arm=held, final_model=details[name], final_fit_wall_s=times[name],
        )
        output[name] = selected
    return output, perf_counter() - began


def infer(document, offer, catalogue, *, method=METHOD):
    return compare(document, offer, catalogue, (method,))[0][method]
