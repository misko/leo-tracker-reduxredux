"""Exact prepared gates for the released named constrained refit."""


from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np


class PreparedNoiseScreen:
    """Keep time-only inputs to the original noise formulas for one row set."""

    def __init__(self, times):
        t = np.asarray(times, float)
        if t.ndim != 1 or len(t) < 4 or not np.isfinite(t).all() or np.ptp(t) <= 0:
            raise ValueError("finite samples and positive time span required")
        self.n = len(t)
        self.x = t - t.mean()
        self.x_norm = np.sqrt(self.x @ self.x)
        tx = self.x / max(float(np.ptp(t)) / 2, 1.0)
        self.design = np.stack([np.ones(self.n), tx, tx * tx], axis=1)
        self.sqrt_n, self.log_n = np.sqrt(self.n), np.log(self.n)
        self.noise_floor = self.n * 75.0**2
        self.splits = np.arange(4, self.n - 3)
        self.later = self.n - self.splits
        self.jump_scale = np.sqrt(1 / self.splits + 1 / self.later)

    def __call__(self, residual):
        r = np.asarray(residual, float)
        if r.ndim != 2 or r.shape[1] != self.n or not np.isfinite(r).all():
            raise ValueError("matching finite residual/time samples required")
        mean = r.mean(axis=1)
        sigma = np.maximum(np.std(r, axis=1, ddof=1, mean=mean[:, None]), 75.0)
        mean_z = np.abs(mean) * self.sqrt_n / sigma
        slope_z = np.abs(r @ self.x) / np.maximum(sigma * self.x_norm, 1e-12)
        fitted = (self.design @ np.linalg.lstsq(self.design, r.T, rcond=None)[0]).T
        rss0 = np.maximum(np.sum(r * r, axis=1), self.noise_floor)
        rss1 = np.maximum(np.sum((r - fitted) ** 2, axis=1), self.noise_floor)
        bic = self.n * np.log(rss0 / rss1) - 3 * self.log_n
        if len(self.splits):
            sums = np.cumsum(r, axis=1)[:, self.splits - 1]
            jump = sums / self.splits - (r.sum(axis=1)[:, None] - sums) / self.later
            step_z = np.max(np.abs(jump) / (sigma[:, None] * self.jump_scale), axis=1)
        else:
            step_z = np.zeros(len(r))
        centered = r - mean[:, None]
        acf = np.sum(centered[:, :-1] * centered[:, 1:], axis=1) / np.maximum(
            np.sum(centered * centered, axis=1), 1e-12
        )
        passed = (mean_z <= 3) & (slope_z <= 3) & (bic <= 10) & (step_z <= 4)
        passed &= np.abs(acf) <= 4 / self.sqrt_n
        return dict(noise_screen_pass=passed, mean_z=mean_z, slope_z=slope_z,
                    quadratic_bic_gain=bic, maximum_step_z=step_z, lag1_acf=acf)


RELEASE_SOURCES = {
    "feasible.py": "a9c5857fcba549f0c8059a544cae7912d4d640dba4af4778689e9aa577807d41",
    "family_cavity.py": "7a20ac84d4c245df95481d10425def01642cbf4d3f45f1f32b9188a78007b3ae",
    "retained_track_likelihood.py": "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf",
    "polynomial_satellite_diagnostics.py": "8bf7d7935b74bba728d437d2652af636e5532be74d798ed4f56c6641be7352c5",
}


class WhiteProfile:
    """Retain the verified stock diagonal and its original scalar contractions."""

    def __init__(self, matrix, period, noise):
        self.matrix, self.period, self.noise = matrix, period, noise
        self.diagonal = np.diag(matrix)
        self.information = self.diagonal @ self.diagonal
        self.constants = {b: (self.information + 1 / b**2, np.log1p(b**2 * self.information)) for b in (300., 1000.)}

    def __call__(self, observed, predicted, bias_sigma):
        y, f = np.asarray(observed), np.atleast_2d(predicted)
        denominator, normalizer = self.constants[bias_sigma]
        raw = y - f
        alias = np.rint(-raw.mean(axis=1) / self.period)
        raw += alias[:, None] * self.period
        z = raw * self.diagonal
        bias = z @ self.diagonal / denominator
        innovations = z - bias[:, None] * self.diagonal
        residual = raw - bias[:, None]
        cost = np.sum(innovations**2, axis=1) + (bias / bias_sigma) ** 2
        cost += 0.0 + normalizer
        return dict(alias=alias, bias=bias, residual=residual, innovations=self.noise * innovations,
                    rms=np.sqrt(np.mean(residual**2, axis=1)), cost=cost)


class GateWork:
    """Reuse time and white-diagonal work for one unchanged cavity configuration."""

    def __init__(self, feasible, likelihood, counts):
        self.stock = feasible.batch_noise_screen
        self.stock_whitening = feasible.whitening
        self.stock_profile = feasible.profile
        self.likelihood, self.counts = likelihood, counts
        self.screens, self.whites, self.profiles = {}, {}, {}

    @staticmethod
    def time_key(times):
        return times.tobytes() if type(times) is np.ndarray and times.ndim == 1 and times.dtype == np.float64 else None

    def screen(self, residual, times):
        key = self.time_key(times)
        if key is None or type(residual) is not np.ndarray or residual.dtype != np.float64 or residual.shape != (1, len(times)):
            self.counts["screen_stock"] += 1
            return self.stock(residual, times)
        prepared = self.screens.get(key)
        if prepared is None:
            start = process_time_ns()
            prepared = self.screens[key] = PreparedNoiseScreen(times)
            self.counts["screen_setup_cpu_ns"] += process_time_ns() - start
            self.counts["screen_preparations"] += 1
        self.counts["screen_calls"] += 1
        return prepared(residual)

    def whitening(self, times, **kwargs):
        key = self.time_key(times)
        if kwargs or key is None:
            self.counts["white_stock"] += 1
            return self.stock_whitening(times, **kwargs)
        cached = self.whites.get(key)
        if cached is None:
            cached = self.whites[key] = self.stock_whitening(times)
            self.counts["white_preparations"] += 1
        self.counts["white_calls"] += 1
        return cached

    def profile(self, observed, predicted, inverse, logvolume=0.0, *, bias_sigma=1000.0):
        key = id(inverse)
        known = self.profiles.get(key)
        if known is None and (type(inverse) is np.ndarray and inverse.ndim == 2 and inverse.dtype == np.float64
                              and inverse.shape[0] == inverse.shape[1] and inverse.flags.c_contiguous):
            diagonal = np.diag(inverse)
            if np.count_nonzero(inverse) == len(diagonal) and np.all(diagonal == 1 / self.likelihood.NOISE):
                known = self.profiles[key] = WhiteProfile(inverse, self.likelihood.PERIOD, self.likelihood.NOISE)
                self.counts["profile_preparations"] += 1
        if (known is None or logvolume != 0.0 or bias_sigma not in (300., 1000.) or type(observed) is not np.ndarray
                or observed.ndim != 1 or type(predicted) is not np.ndarray or predicted.ndim not in (1, 2)
                or predicted.shape[-1] != len(observed) or inverse.shape[0] != len(observed)):
            self.counts["profile_stock"] += 1
            return self.stock_profile(observed, predicted, inverse, logvolume, bias_sigma=bias_sigma)
        self.counts["profile_calls"] += 1
        return known(observed, predicted, bias_sigma)


@contextmanager
def gate_binding(feasible, cavity, likelihood, counts, *, use_white=True):
    """Apply only inside the constrained optimizer; admission and final gates remain stock."""
    original, fit = cavity.constrained, feasible.feasible_fit

    def constrained(*args, **kwargs):
        work = GateWork(feasible, likelihood, counts)
        counts["constrained_calls"] += 1

        def run_fit(*values, **options):
            start = process_time_ns()
            whitening = work.whitening if use_white else work.stock_whitening
            profile = work.profile if use_white else work.stock_profile
            with (patch.object(feasible, "batch_noise_screen", work.screen),
                  patch.object(feasible, "whitening", whitening), patch.object(feasible, "profile", profile)):
                result = fit(*values, **options)
            counts["fit_cpu_ns"] += process_time_ns() - start
            counts["phase_fits"] += 1
            counts["visits"] += result["evaluations"]
            return result

        start = process_time_ns()
        with patch.object(feasible, "feasible_fit", run_fit):
            result = original(*args, **kwargs)
        counts["constrained_cpu_ns"] += process_time_ns() - start
        return result

    with patch.object(cavity, "constrained", constrained):
        yield


def validate_released_ports(feasible, cavity, likelihood, noise):
    for module in (feasible, cavity, likelihood, noise):
        path = Path(module.__file__)
        if sha256(path.read_bytes()).hexdigest() != RELEASE_SOURCES[path.name]:
            raise ValueError(f"Unrecognized installed {path.name} source")
    if (cavity.constrained is not feasible.constrained or feasible.profile is not likelihood.profile
            or feasible.whitening is not likelihood.whitening or feasible.batch_noise_screen is not noise.batch_noise_screen):
        raise ValueError("The original constrained gate ports are already modified")
