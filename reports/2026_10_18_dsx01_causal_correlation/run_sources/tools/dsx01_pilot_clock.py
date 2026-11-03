"""Pure-array, frame-local carrier/symbol-clock diagnostic on known pilots.

This research kernel profiles eight complex channel gains independently in
each frame. It neither links frame carrier phases nor estimates satellite IDs.
Only public pilot templates are imported from the production analyzer.
"""

from dataclasses import dataclass

import numpy as np

from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)


@dataclass
class ClockFit:
    residual_cfo_hz: float
    symbol_clock_ppm: float
    explained_fraction: float
    residual_energy: float
    evaluations: int
    boundary: bool
    converged: bool


def minimize_profile(fun, start, bounds):
    """Small bounded damped-Newton search; no new numerical dependency."""
    x = np.array(start, dtype=float)
    lower, upper = np.array(bounds).T
    value, gradient = fun(x)
    evaluations = 1
    converged = False
    for _ in range(60):
        columns = []
        for delta in np.eye(len(x)) * 1e-4:
            columns.append((fun(x + delta)[1] - fun(x - delta)[1]) / 2e-4)
        evaluations += 2 * len(x)
        hessian = np.stack(columns, axis=1)
        hessian = (hessian + hessian.T) / 2
        eigenvalues, vectors = np.linalg.eigh(hessian)
        hessian = (vectors * np.maximum(eigenvalues, 1e-5)) @ vectors.T
        projected_gradient = x - np.clip(x - gradient, lower, upper)
        if np.max(abs(projected_gradient)) < 1e-9:
            converged = True
            break
        step = -np.linalg.solve(hessian, gradient)
        step /= max(1, np.max(abs(step)))
        improved = False
        for power in range(20):
            trial = np.clip(x + step * 0.5**power, lower, upper)
            trial_value, trial_gradient = fun(trial)
            evaluations += 1
            if trial_value < value:
                change = np.max(abs(trial - x))
                x, value, gradient = trial, trial_value, trial_gradient
                improved = True
                if change < 1e-8:
                    converged = True
                break
        if converged or not improved:
            converged |= np.max(abs(projected_gradient)) < 1e-7
            break
    return x, value, evaluations, bool(converged)


class FrameClock:
    """Profile y = B_k(t) a_k exp(i2πt(δf + f_k ε)) + noise.

    Positive epsilon means faster received OFDM symbol/tone evolution. It is a
    received clock relative to the sample grid, not a transmitter-only clock.
    Guarded samples remain in the same OFDM symbol throughout the search box.
    Delay and channel phase are deliberately not separately identified.
    """

    def __init__(self, samples, rate, epoch, acquired_cfo, edge, *, roll=0, half=None):
        y = np.asarray(samples, dtype=np.complex128)
        if y.ndim != 1 or not np.isfinite(y).all():
            raise ValueError("finite one-dimensional IQ required")
        if not np.isfinite([rate, epoch, acquired_cfo]).all() or rate < 2_000_000:
            raise ValueError("unsupported sample geometry")
        start = int(np.ceil(epoch + 2 * OFDM_SYMBOL_DURATION_S * rate))
        stop = int(np.floor(epoch + 302 * OFDM_SYMBOL_DURATION_S * rate))
        if start < 0 or stop > len(y):
            raise ValueError("one complete known-pilot frame required")
        index = np.arange(start, stop)
        time = (index - epoch) / rate
        symbol = np.floor(time / OFDM_SYMBOL_DURATION_S + 1e-10).astype(int)
        local = time - symbol * OFDM_SYMBOL_DURATION_S
        mask = (symbol >= 2) & (symbol <= 301)
        # 0.6 sample guard exceeds the largest 100-ppm dilation in a frame.
        mask &= local >= CYCLIC_PREFIX_DURATION_S + 0.6 / rate
        mask &= local <= OFDM_SYMBOL_DURATION_S - 0.6 / rate
        if half is not None:
            if half not in (0, 1):
                raise ValueError("half must be zero or one")
            mask &= (symbol < 152) if half == 0 else (symbol >= 152)
        index, time, symbol, local = [v[mask] for v in (index, time, symbol, local)]
        self.frequencies = np.asarray(edge_frequencies_hz(edge))
        self.time = time - np.mean(time)
        known = qin_edge_pilot_symbols(edge, symbol_roll=roll)[symbol - 2]
        self.basis = (
            known
            * np.exp(2j * np.pi * (local - CYCLIC_PREFIX_DURATION_S)[:, None] * self.frequencies)
            / np.sqrt(8)
        )
        self.values = y[index] * np.exp(-2j * np.pi * acquired_cfo * index / rate)
        self.energy = float(np.vdot(self.values, self.values).real)
        if self.energy <= 1e-20:
            raise ValueError("nonzero IQ energy required")
        self.phase_derivative = np.stack(
            (
                2j * np.pi * self.time[:, None] * 500 * np.ones((1, 8)),
                2j * np.pi * self.time[:, None] * self.frequencies * 50e-6,
            )
        )

    def objective(self, coordinates):
        phase = np.einsum("p,pnk->nk", coordinates, self.phase_derivative)
        design = self.basis * np.exp(phase)
        gram = design.conj().T @ design
        rhs = design.conj().T @ self.values
        gains = np.linalg.solve(gram, rhs)
        residual = self.values - design @ gains
        objective = float(np.vdot(residual, residual).real) / self.energy
        derivative = (
            -2
            * np.real(
                np.einsum("n,pnk,k->p", residual.conj(), self.phase_derivative * design, gains)
            )
            / self.energy
        )
        return objective, derivative

    def fit(self, *, symbol_clock=True):
        dimensions = 2 if symbol_clock else 1
        bounds = [(-2.0, 2.0), (-2.0, 2.0)][:dimensions]

        def fun(x):
            coordinates = np.zeros(2)
            coordinates[:dimensions] = x
            value, jac = self.objective(coordinates)
            return value, jac[:dimensions]

        # Common deterministic carrier starts, independent of any orbit or GPS.
        fits = [
            minimize_profile(fun, np.array([start, 0.0])[:dimensions], bounds)
            for start in (-1.5, 0.0, 1.5)
        ]
        best_x, best_value, _, converged = min(fits, key=lambda r: r[1])
        x = np.zeros(2)
        x[:dimensions] = best_x
        return ClockFit(
            residual_cfo_hz=float(x[0] * 500),
            symbol_clock_ppm=float(x[1] * 50),
            explained_fraction=float(1 - best_value),
            residual_energy=float(best_value * self.energy),
            evaluations=sum(r[2] for r in fits),
            boundary=bool(np.any(abs(best_x) >= 1.9999)),
            converged=converged,
        )


class WindowClock(FrameClock):
    """Common frequency over a short window, with independent frame channels."""

    def __init__(self, frames):
        self.frames = tuple(frames)
        if not self.frames:
            raise ValueError("at least one frame required")
        self.energy = sum(frame.energy for frame in self.frames)

    def objective(self, coordinates):
        values = [frame.objective(coordinates) for frame in self.frames]
        weights = np.array([frame.energy / self.energy for frame in self.frames])
        return (
            float(weights @ np.array([v[0] for v in values])),
            np.sum(weights[:, None] * np.array([v[1] for v in values]), axis=0),
        )


def differential_chirp(first, second, rate, epoch):
    """Template-free RX frequency-difference/chirp check on aligned IQ.

    A distinct complex cross-channel gain is profiled in each complete frame;
    this never assumes inter-frame phase continuity. The result is descriptive
    correlation evidence, not emitter identity or a radio calibration prior.
    """
    a, b = np.asarray(first), np.asarray(second)
    if a.ndim != 1 or b.shape != a.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("equal finite IQ vectors required")
    product = a * b.conj()
    transform = np.fft.fft(product, n=131072)
    coarse = float(np.fft.fftfreq(131072, 1 / rate)[np.argmax(abs(transform))])
    times = np.arange(len(a)) / rate
    centered = times - (epoch / rate + 7 / 750)
    product = product * np.exp(-2j * np.pi * coarse * times)
    pieces = []
    for frame in range(14):
        start = int(np.ceil(epoch + (frame / 750 + 2 * OFDM_SYMBOL_DURATION_S) * rate))
        stop = int(np.floor(epoch + (frame / 750 + 302 * OFDM_SYMBOL_DURATION_S) * rate))
        if start < 0 or stop > len(a):
            continue
        z, t = product[start:stop], centered[start:stop]
        features = 2j * np.pi * np.stack((1000 * t, 25000 * t**2))
        pieces.append((z, features))
    energy = sum(float(np.vdot(z, z).real) for z, _ in pieces)
    if not pieces or energy <= 1e-20:
        raise ValueError("complete frames with nonzero energy required")

    def fun(x):
        x = np.asarray(x)
        gain_energy, gradient = 0.0, np.zeros(2)
        for z, features in pieces:
            dechirped = z * np.exp(-x @ features)
            rhs = np.sum(dechirped)
            derivative = -features @ dechirped
            gain_energy += abs(rhs) ** 2 / len(z)
            gradient -= 2 * np.real(rhs.conjugate() * derivative) / len(z) / energy
        return 1 - gain_energy / energy, gradient

    fits = [
        minimize_profile(fun, (f, r), [(-1, 1), (-2, 2)])
        for f in (-0.75, 0, 0.75)
        for r in (-1, 0, 1)
    ]
    x, value, _, converged = min(fits, key=lambda r: r[1])
    constant = [
        minimize_profile(lambda v: (fun([v[0], 0])[0], fun([v[0], 0])[1][:1]), [f], [(-1, 1)])
        for f in (-0.75, 0, 0.75)
    ]
    xc, vc, _, _ = min(constant, key=lambda r: r[1])
    return dict(
        frequency_difference_hz=float(coarse + 1000 * x[0]),
        difference_rate_hz_s=float(50000 * x[1]),
        explained_fraction=float(1 - value),
        constant_frequency_difference_hz=float(coarse + 1000 * xc[0]),
        constant_explained_fraction=float(1 - vc),
        converged=converged,
        frames=len(pieces),
        evaluations=sum(f[2] for f in fits) + sum(f[2] for f in constant),
        boundary=bool(np.any(abs(x) >= np.array([0.9999, 1.9999]))),
    )


def synthetic_frame(
    *,
    rate=2_500_000,
    edge="lower",
    cfo=0.0,
    ppm=0.0,
    epoch=10.27,
    gains=None,
    roll=0,
    seed=1,
    noise=0.0,
):
    """Analytic waveform, including scaled symbol boundaries; no interpolation."""
    time = (np.arange(int(np.ceil(epoch + 304 * OFDM_SYMBOL_DURATION_S * rate))) - epoch) / rate
    scaled = time * (1 + ppm * 1e-6)
    symbol = np.floor(scaled / OFDM_SYMBOL_DURATION_S).astype(int)
    valid = (symbol >= 2) & (symbol <= 301)
    local = scaled[valid] - symbol[valid] * OFDM_SYMBOL_DURATION_S
    known = qin_edge_pilot_symbols(edge, symbol_roll=roll)[symbol[valid] - 2]
    gain = np.ones(8) if gains is None else np.asarray(gains)
    output = np.zeros(len(time), dtype=np.complex128)
    output[valid] = np.sum(
        known
        * gain
        * np.exp(
            2j * np.pi * (local - CYCLIC_PREFIX_DURATION_S)[:, None] * edge_frequencies_hz(edge)
        ),
        axis=1,
    ) / np.sqrt(8)
    output *= np.exp(2j * np.pi * cfo * np.arange(len(time)) / rate)
    rng = np.random.default_rng(seed)
    output += noise * (rng.normal(size=len(time)) + 1j * rng.normal(size=len(time))) / np.sqrt(2)
    return output
