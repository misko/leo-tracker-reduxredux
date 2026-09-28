"""Pure diagnostics for frozen satellite identities and receiver locations."""
import numpy as np


def fit_profiles(times, measured, predicted, train, taus):
    times, measured, predicted = map(np.asarray, (times, measured, predicted))
    train = np.asarray(train, dtype=bool)
    if not train.any() or not (~train).any():
        raise ValueError('nonempty training and scoring partitions required')
    residual = measured[None, :] - predicted
    offsets = residual[:, train].mean(axis=1)
    centered = residual - offsets[:, None]
    return {'tau_s': np.asarray(taus).tolist(), 'offset_hz': offsets.tolist(),
            'train_rms_hz': np.sqrt(np.mean(centered[:, train]**2, axis=1)).tolist(),
            'score_rms_hz': np.sqrt(np.mean(centered[:, ~train]**2, axis=1)).tolist()}, centered


def select_fit(profile, centered, times, train, bound):
    taus = np.asarray(profile['tau_s'])
    eligible = np.flatnonzero(np.abs(taus) <= bound)
    idx = int(eligible[np.argmin(np.asarray(profile['train_rms_hz'])[eligible])])
    train = np.asarray(train, dtype=bool)
    times = np.asarray(times)
    x = times-times[train].mean()
    denom = float(x[train] @ x[train])
    if denom <= 0:
        raise ValueError('training times must vary')
    slope = float(x[train] @ centered[idx, train] / denom)
    detrended = centered[idx]-slope*x
    return {'tau_s':float(taus[idx]), 'offset_hz':profile['offset_hz'][idx],
            'train_rms_hz':profile['train_rms_hz'][idx], 'score_rms_hz':profile['score_rms_hz'][idx],
            'boundary':bool(abs(taus[idx])==bound), 'residual_slope_hz_per_s':slope,
            'residual_drift_over_span_hz':slope*float(np.ptp(times)),
            'linear_drift_train_rms_hz':float(np.sqrt(np.mean(detrended[train]**2))),
            'linear_drift_score_rms_hz':float(np.sqrt(np.mean(detrended[~train]**2)))}
