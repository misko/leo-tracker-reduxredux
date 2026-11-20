"""Whiten an irregular Doppler time series with a scalar Gaussian state model."""

import numpy as np
from scipy.linalg import solve_banded

from . import robust_em as lean


class _Transpose:
    __array_priority__ = 1000

    def __init__(self, operator):
        self.operator = operator

    def __rmatmul__(self, values):
        return self.operator.apply(np.asarray(values).T).T


class InnovationFilter:
    """Inverse Cholesky action for white noise plus stationary exponential covariance."""

    def __init__(self, times, white_sd, correlated_sd, correlation_time):
        times = np.asarray(times, dtype=float)
        spacing = np.diff(times)
        if (
            times.ndim != 1
            or not len(times)
            or not np.isfinite(times).all()
            or not (spacing > 0).all()
            or not np.isfinite([white_sd, correlated_sd, correlation_time]).all()
            or white_sd <= 0
            or correlated_sd < 0
            or correlation_time <= 0
        ):
            raise ValueError("expected ordered times, positive white noise and positive time scale")
        self.decay = np.exp(-spacing / correlation_time)
        white, stationary = white_sd**2, correlated_sd**2
        transition_variance = -stationary * np.expm1(-2 * spacing / correlation_time)
        predicted_variance = np.empty(len(times))
        predicted_variance[0] = stationary
        for i, decay in enumerate(self.decay):
            prior = predicted_variance[i]
            posterior = white * prior / (white + prior)
            predicted_variance[i + 1] = decay**2 * posterior + transition_variance[i]
        self.innovation_sd = np.sqrt(white + predicted_variance)
        # e[i] = (y[i] - decay*y[i-1])/sd[i] + feedback*e[i-1].
        # A lower bidiagonal solve applies the recurrence to every column.
        self.bands = np.zeros((2, len(times)))
        self.bands[0] = 1
        self.bands[1, :-1] = (
            -self.decay * white / (self.innovation_sd[1:] * self.innovation_sd[:-1])
        )
        self.T = _Transpose(self)
        self.constant = self.apply(np.ones(len(times)))
        self.constant.setflags(write=False)

    @property
    def nbytes(self):
        return sum(x.nbytes for x in (self.decay, self.innovation_sd, self.bands, self.constant))

    def apply(self, values):
        values = np.asarray(values, dtype=float)
        if values.ndim not in (1, 2) or values.shape[0] != len(self.innovation_sd):
            raise ValueError("expected a time vector or a time-by-column matrix")
        columns = values.reshape(len(self.innovation_sd), -1)
        rhs = columns.copy(order="F")
        rhs[1:] -= self.decay[:, None] * columns[:-1]
        rhs /= self.innovation_sd[:, None]
        if len(rhs) > 1 and rhs.shape[1]:
            rhs = solve_banded((1, 0), self.bands, rhs, overwrite_b=True, check_finite=False)
        return rhs.reshape(values.shape)

    def __matmul__(self, values):
        return self.apply(values)

    def sum(self, *, axis):
        if axis != 1:
            raise ValueError("only the constant-vector projection is required")
        return self.constant


def observations(document):
    """Apply the native track validity, duplicate and curvature rules before whitening."""
    duration = float(document["duration_s"])
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError("invalid capture duration")
    inputs = []
    for arc in document["tracks"]:
        t = np.asarray(arc["times"], dtype=float)
        y = np.asarray(arc["values"], dtype=float)
        rx, ch, frequency = arc["receiver"], arc["channel"], float(arc["rf_hz"])
        if (
            t.ndim != 1
            or t.shape != y.shape
            or not np.isfinite(t).all()
            or not np.isfinite(y).all()
            or np.any(np.diff(t) <= 0)
            or (len(t) and (t[0] < 0 or t[-1] > duration))
            or rx not in (1, 2)
            or ch not in range(1, 9)
            or not 1e9 < frequency < 100e9
        ):
            raise ValueError("invalid anonymous track or capture support")
        inputs.append((t, y, int(rx), int(ch), frequency))
    seen, tracks = set(), []
    duplicates = undersized = 0
    for t, y, rx, ch, frequency in sorted(inputs, key=lambda item: -len(item[0])):
        keys = [
            (rx, ch, frequency, round(s, 6), round(f, 3))
            for s, f in zip(t, lean.fold(y), strict=True)
        ]
        keep = np.fromiter((key not in seen for key in keys), dtype=bool, count=len(t))
        duplicates += int(np.count_nonzero(~keep))
        t, y = t[keep], y[keep]
        if len(t) < 4:
            undersized += len(t)
            continue
        seen.update(keys)
        dt, dy = t - t.mean(), y - y.mean()
        curvature = dy - dt * ((dy @ dt) / (dt @ dt))
        tracks.append(
            lean.Track(
                t,
                y,
                frequency,
                2 * (rx - 1) + int(ch > 4),
                bool(np.ptp(t) >= 20 and np.sqrt(np.mean(curvature**2)) >= 250),
                (t - duration / 2) / 100,
                InnovationFilter(t, lean.WHITE_HZ, lean.CORRELATED_HZ, lean.CORRELATION_S),
            )
        )
    return tracks, dict(
        input_tracks=len(inputs),
        input_points=sum(len(row[0]) for row in inputs),
        unique_fit_points=sum(len(track.t) for track in tracks),
        duplicates_removed=duplicates,
        undersized_points_excluded=undersized,
        curved_tracks=sum(track.curved for track in tracks),
        dense_noise_bytes=8 * sum(len(track.t) ** 2 for track in tracks),
        filter_noise_bytes=sum(track.whiten.nbytes for track in tracks),
    )
