"""Training-sample-only fractional pilot fit with one channel per tone/frame.

This RF research workspace has no geographic, satellite, or TLE inputs.  The
three nonlinear coordinates are carrier, fractional epoch, and modulation rate.
Complex tone gains and DC are eliminated independently in each supplied frame.
"""

from functools import lru_cache

import numpy as np

from ds23_fractional_differential_phase import isolated_channel_waves
from ds23_training_gain_rf import restricted_workspace
from fast_local_pilot_refinement import FastPilotWorkspace
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    CYCLIC_PREFIX_DURATION_S,
    OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz,
    qin_edge_pilot_symbols,
)
from probe_native_code_carrier import periodic_upsample


def projected_frame_gains(coefficients, covariance, training):
    """Project row coefficients; propagate the covariance of column coefficients.

    For gain = c(row) @ w, Var(gain) = w.T @ Cov(c(column)) @ w.conj().
    The alternative w.H @ Cov @ w is wrong for complex, non-diagonal Cov.
    """
    c, cov = np.asarray(coefficients), np.asarray(covariance)
    training = np.asarray(training, bool)
    if c.ndim != 2 or training.shape != (len(c),) or cov.shape != (len(c), c.shape[1], c.shape[1]) or training.sum() < 4:
        raise ValueError('matching complex frame coefficients/covariance and four training frames required')
    if not np.isfinite(c).all() or not np.isfinite(cov).all():
        raise ValueError('finite complex frame coefficients and covariance required')
    _, singular, vh = np.linalg.svd(c[training], full_matrices=False)
    direction = vh[0].conj()
    gain = c @ direction
    variance = np.einsum('i,nij,j->n', direction, cov, direction.conj()).real
    if np.any(variance <= 0):
        raise ValueError('positive projected extraction variance required')
    return dict(gain=gain, variance=variance,
        training_rank_one_fraction=float(singular[0]**2/np.sum(singular**2)))


@lru_cache(maxsize=8)
def tone_waves(fs, edge, control=False):
    if not control:
        result = np.column_stack(isolated_channel_waves(fs, edge))
    else:
        t = np.arange(int(np.ceil(fs / 750))) / fs
        symbol = np.floor(t / OFDM_SYMBOL_DURATION_S).astype(int)
        keep = (symbol >= 2) & (symbol < 302)
        local = t[keep] - symbol[keep] * OFDM_SYMBOL_DURATION_S
        frame = np.zeros((len(t), 8), complex)
        symbols = qin_edge_pilot_symbols(edge, symbol_roll=CONTROL_SYMBOL_ROLL)
        frame[keep] = symbols[symbol[keep] - 2] * np.exp(
            2j * np.pi * (local[:, None] - CYCLIC_PREFIX_DURATION_S)
            * edge_frequencies_hz(edge)[None]
        ) / np.sqrt(8)
        result = np.column_stack([periodic_upsample(frame[:, k], 32) for k in range(8)])
    result.flags.writeable = False
    return result


class TrainingChannelWorkspace(FastPilotWorkspace):
    """Use only explicitly supplied, disjoint physical IQ segments."""

    def __init__(self, samples, fs, edge, epoch, segments):
        # Reuse the validated support contract, including the frame/raw-energy
        # restriction. No inherited scorer or objective sees other IQ samples.
        restricted = restricted_workspace(samples, fs, edge, epoch, segments)
        self.__dict__.update(restricted.__dict__)
        self.edge = edge
        self._columns_cache = {}

    def columns(self, parameters, *, derivatives=False, control=False):
        f, offset, ppm = np.asarray(parameters, float)
        if not np.isfinite([f, offset, ppm]).all():
            raise ValueError('finite carrier, epoch, and rate required')
        key = (float(f), float(offset), float(ppm), bool(control))
        if key != self._columns_cache.get('key'):
            a = 1 + ppm * 1e-6
            u = (self.n - self.epoch - offset) * a
            local = u - np.floor(u / self.period) * self.period
            position = local * 32
            index = np.floor(position).astype(np.int64)
            fraction = position - index
            wave = tone_waves(self.fs, self.edge, control)
            left = wave[index % len(wave)]
            right = wave[(index + 1) % len(wave)]
            rotation = np.exp(2j * np.pi * f * (self.t - self.mid))[:, None]
            values = (left + (right - left) * fraction[:, None]) * rotation
            slope = (right - left) * rotation * 32
            self._columns_cache = dict(key=key, values=values, slope=slope)
        values = self._columns_cache['values']
        if not derivatives:
            return values
        slope = self._columns_cache['slope']
        derivatives = (
            2j * np.pi * (self.t - self.mid)[:, None] * values * 100,
            -(1 + ppm * 1e-6) * slope,
            (self.n - self.epoch - offset)[:, None] * 1e-6 * slope * 20,
        )
        return values, derivatives

    def statistics(self, parameters, subset='all', derivatives=True, *, control=False):
        if subset not in ('all', 'odd', 'even'):
            raise ValueError('named frame subset required')
        if derivatives:
            columns, derivative = self.columns(parameters, derivatives=True, control=control)
        else:
            columns = self.columns(parameters, control=control)
        normal, rhs = np.zeros((3, 3)), np.zeros(3)
        explained = raw = 0.
        count = frames = 0
        for k, ix in enumerate(self.frames):
            if subset == 'odd' and k % 2 == 0 or subset == 'even' and k % 2 == 1:
                continue
            basis = columns[ix] - columns[ix].mean(axis=0)
            y = self.y[ix] - self.raw_sum[k] / len(ix)
            gram = basis.conj().T @ basis
            cross = basis.conj().T @ y
            coefficient = np.linalg.solve(gram, cross)
            residual = y - basis @ coefficient
            explained += float(np.vdot(cross, coefficient).real)
            raw += self.raw_energy[k]
            count += len(ix)
            frames += 1
            if derivatives:
                d = np.column_stack([v[ix] @ coefficient for v in derivative])
                d -= d.mean(axis=0)
                projected_cross = basis.conj().T @ d
                projected = d - basis @ np.linalg.solve(gram, projected_cross)
                normal += (projected.conj().T @ projected).real
                rhs += (d.conj().T @ residual).real
        return dict(score=float(explained / max(raw, 1e-20)), normal=normal,
            rhs=rhs, gradient_score=2 * rhs / max(raw, 1e-20), raw_energy=raw,
            residual_energy=float(raw - explained), sample_count=count, frames=frames)

    def evaluate(self, frequencies, offset=0., ppm=0., subset='all', control=False, details=False):
        if details:
            raise ValueError('use explicit frame coefficient extraction')
        return np.array([self.statistics([f, offset, ppm], subset, False,
            control=control)['score'] for f in np.atleast_1d(frequencies)])

    def fit_from_training_seed(self, seed, center, *, iterations=16, radius=800.):
        start = [seed['CFO_hz'], seed['offset_samples'], seed['modulation_ppm']]
        fit = self.optimize(start, center, radius=radius, iterations=iterations)
        f, offset, ppm = fit['parameters']
        statistics = self.statistics(fit['parameters'])
        control = self.statistics(fit['parameters'], derivatives=False, control=True)['score']
        noise = statistics['residual_energy'] / max(
            1, statistics['sample_count'] - 9 * statistics['frames'])
        covariance = np.linalg.pinv(statistics['normal'], rcond=1e-12) * noise / 2
        covariance *= self.parameter_scale[:, None] * self.parameter_scale[None, :]
        return dict(CFO_hz=float(f), offset_samples=float(offset), modulation_ppm=float(ppm),
            score=statistics['score'], control_score=control, margin=statistics['score']-control,
            frequency_search_boundary=bool(abs(f-center) >= radius-.5),
            epoch_search_boundary=bool(abs(offset) >= .75-1e-5),
            code_rate_search_boundary=bool(abs(ppm) >= 40-1e-4),
            conditional_covariance=covariance, covariance_is_local_Gaussian_proxy_not_calibrated=True,
            optimizer_calls=fit['calls'], selected_history=fit['history'],
            training_only_flat_seed=True, tone_coefficients_per_frame=8)
