"""Orbit-blind short carrier segments; no satellite, position or target labels."""
from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class Configuration:
    window_s: float = 20.
    stride_s: float = 10.
    minimum_points: int = 8
    minimum_span_s: float = 6.
    maximum_gap_s: float = 4.
    residual_limit_hz: float = 300.
    maximum_slope_hz_s: float = 20000.
    maximum_curvature_hz_s2: float = 2000.
    random_triples: int = 256
    segments_per_window: int = 3
    selection_bin_s: float = 20.
    segments_per_bin: int = 2
    alias_period_hz: float = 227272.72727272726
    seed: int = 824019

    def __post_init__(self):
        values = asdict(self)
        if any(not np.isfinite(v) or v <= 0 for v in values.values()):
            raise ValueError('All configuration values must be finite and positive')
        if self.minimum_points < 4 or self.minimum_span_s > self.window_s:
            raise ValueError('Insufficient quadratic support or inconsistent window')


def circular(value, period):
    return (value + period / 2) % period - period / 2


def _fit(t, y, coefficient, active, config):
    """Refine an alias-aware hypothesis, then retain only connected support."""
    design = np.column_stack([np.ones(len(t)), t, t*t])
    for _ in range(4):
        prediction = design @ coefficient
        residual = circular(y - prediction, config.alias_period_hz)
        take = active & (abs(residual) <= config.residual_limit_hz)
        if take.sum() < config.minimum_points:
            return None
        coefficient = np.linalg.lstsq(design[take], (prediction + residual)[take], rcond=None)[0]
    residual = circular(y - design @ coefficient, config.alias_period_hz)
    take = np.flatnonzero(active & (abs(residual) <= config.residual_limit_hz))
    chunks = np.split(take, np.flatnonzero(np.diff(t[take]) > config.maximum_gap_s) + 1)
    eligible = [chunk for chunk in chunks if len(chunk) >= config.minimum_points
                and np.ptp(t[chunk]) >= config.minimum_span_s]
    if not eligible:
        return None
    # Each output is one connected interval, never a bridge across missing data.
    take = max(eligible, key=lambda chunk: (len(chunk), np.ptp(t[chunk]), -int(chunk[0])))
    slope = coefficient[1] + 2*coefficient[2]*t[take]
    if max(abs(slope)) > config.maximum_slope_hz_s or 2*abs(coefficient[2]) > config.maximum_curvature_hz_s2:
        return None
    residual = residual[take]
    centered = t[take] - np.mean(t[take])
    nonlinear = coefficient[2] * centered**2
    line = np.column_stack([np.ones(len(take)), centered])
    nonlinear -= line @ np.linalg.lstsq(line, nonlinear, rcond=None)[0]
    rms = float(np.sqrt(np.mean(residual**2)))
    # Curvature information in units of a 125 Hz carrier measurement. This is
    # only a proposal ranking, never a satellite likelihood or physical proof.
    information = float(np.linalg.norm(nonlinear) / max(125., rms))
    return dict(indices=take, coefficient=coefficient, rms_hz=rms,
                span_s=float(np.ptp(t[take])), information=information)


def extract(observations, config=Configuration()):
    t = np.asarray(observations.times_s, float)
    y = np.asarray(observations.measured_hz, float)
    rx = np.asarray(observations.receiver)
    channel = np.asarray(observations.channel)
    rf = np.asarray(observations.rf_hz, float)
    if t.ndim != 1 or any(a.shape != t.shape for a in [y, rx, channel, rf]):
        raise ValueError('Observation arrays must have the same one-dimensional shape')
    if any(np.any(~np.isfinite(a)) for a in [t, y, rx, channel, rf]):
        raise ValueError('Observation values must be finite')
    if not len(t):
        return dict(configuration=asdict(config), proposals=[], selected=[])
    rng = np.random.default_rng(config.seed)
    proposals = []
    lanes = sorted(set(zip(rx.tolist(), channel.tolist(), rf.tolist())))
    for receiver, ch, frequency in lanes:
        lane = np.flatnonzero((rx == receiver) & (channel == ch) & (rf == frequency))
        lane = lane[np.argsort(t[lane], kind='stable')]
        start = np.floor(t[lane].min() / config.stride_s)*config.stride_s
        for left in np.arange(start, t[lane].max() + .001, config.stride_s):
            rows = lane[(t[lane] >= left) & (t[lane] < left + config.window_s)]
            if len(rows) < config.minimum_points or np.ptp(t[rows]) < config.minimum_span_s:
                continue
            tt = t[rows] - (left + config.window_s / 2)
            yy = y[rows]
            design = np.column_stack([np.ones(len(rows)), tt, tt*tt])
            # A real segment can start/end inside a window. Requiring a point
            # in each window third silently excludes those shorter segments.
            triples = np.sort(rng.integers(0,len(rows),(config.random_triples,3)),axis=1)
            valid = ((np.diff(tt[triples],axis=1)>0).all(axis=1) &
                     (np.ptp(tt[triples], axis=1) >= config.minimum_span_s))
            triples = triples[valid]
            if not len(triples):
                continue
            # Unknown integer aliases are nuisance variables of the proposal.
            # The anchor fixes their common gauge; adjacent samples need not
            # remain within one alias interval over a complete window.
            target = yy[triples]
            relative = circular(target - target[:, :1], config.alias_period_hz) + target[:, :1]
            coefficients = []
            for second in [-1, 0, 1]:
                for third in [-1, 0, 1]:
                    lifted = relative + config.alias_period_hz*np.array([0, second, third])
                    coefficients.append(np.linalg.solve(design[triples], lifted[..., None])[..., 0])
            coefficients = np.concatenate(coefficients)
            slopes = coefficients[:, 1, None] + 2*coefficients[:, 2, None]*tt[[0, -1]]
            keep = ((abs(slopes).max(axis=1) <= config.maximum_slope_hz_s) &
                    (2*abs(coefficients[:, 2]) <= config.maximum_curvature_hz_s2))
            coefficients = coefficients[keep]
            if not len(coefficients):
                continue
            residual = circular(yy[None, :] - coefficients @ design.T, config.alias_period_hz)
            active = np.ones(len(rows), bool)
            for _ in range(config.segments_per_window):
                counts = np.sum((abs(residual) <= config.residual_limit_hz) & active, axis=1)
                # Refine several promising seeds; a crossing's mixed triple
                # must not prevent a cleaner lower-ranked hypothesis winning.
                candidates = []
                for index in np.argsort(-counts, kind='stable')[:12]:
                    if counts[index] < config.minimum_points:
                        break
                    fit = _fit(tt, yy, coefficients[index], active, config)
                    if fit is not None:
                        candidates.append(fit)
                if not candidates:
                    break
                fit = min(candidates, key=lambda f: (-len(f['indices']), f['rms_hz'], -f['span_s']))
                ix = fit.pop('indices')
                active[ix] = False
                proposals.append(dict(rows=tuple(map(int, rows[ix])), receiver=int(receiver),
                    channel=int(ch), rf_hz=float(frequency), center_s=float(np.mean(t[rows[ix]])),
                    window_left_s=float(left), coefficient=fit.pop('coefficient').tolist(), **fit))
    # Fixed chronological strata prevent one channel or time interval consuming
    # all proposal slots. Near-duplicate windows do not multiply evidence.
    selected = []
    for receiver, ch, frequency in lanes:
        choices = [p for p in proposals if (p['receiver'], p['channel'], p['rf_hz']) == (receiver, ch, frequency)]
        used = set()
        edges = np.arange(np.floor(t.min()/config.selection_bin_s)*config.selection_bin_s,
                          t.max()+config.selection_bin_s,config.selection_bin_s)
        for left, right in zip(edges[:-1], edges[1:]):
            for _ in range(config.segments_per_bin):
                eligible = [p for p in choices if left <= p['center_s'] < right and
                            len(set(p['rows']) - used) >= config.minimum_points]
                if not eligible:
                    break
                best = min(eligible, key=lambda p: (-p['information'], p['rms_hz'], -p['span_s'], p['rows']))
                selected.append(best)
                used.update(best['rows'])
    return dict(configuration=asdict(config), proposals=proposals, selected=selected)
