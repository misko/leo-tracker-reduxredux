"""RF-only simultaneous frame-epoch registration between synchronized RXs.

This is an association proposal, not proof that two signals share a satellite.
Several distinct simultaneous frame epochs and held-time prediction are needed
before a common circular frequency offset can serve as calibration evidence.
"""

import numpy as np

PERIOD = 1 / 4.4e-6


def wrap(value, period=PERIOD):
    return (np.asarray(value) + period/2) % period - period/2


def unique_peaks(candidates, fs):
    output = []
    passing = [p for p in candidates if p['passed_fractional_margin_gate']]
    for p in sorted(passing, key=lambda p: -p['fractional_margin']):
        epoch = p['integer_epoch_sample'] + p['fractional_epoch_offset_samples']
        cfo = p['fractional_tracking_cfo_hz']
        if not np.isfinite([epoch, cfo, p['fractional_margin']]).all():
            raise ValueError('finite native peak evidence required')
        if any(abs(wrap(epoch-q['epoch'], fs/750)) < fs*120e-9
               and abs(wrap(cfo-q['cfo'])) < 250 for q in output):
            continue
        output.append(dict(epoch=float(epoch), cfo=float(cfo),
                           margin=float(p['fractional_margin']), rank=p['candidate_rank']))
    return output


def epoch_pairs(first, second, fs, *, tolerance_samples=None, tolerance_seconds=80e-9):
    tolerance=(fs*tolerance_seconds if tolerance_samples is None else tolerance_samples)
    if not np.isfinite([fs,tolerance]).all() or fs<=0 or not 0<tolerance/fs<=800e-9:
        raise ValueError('positive rate and bounded physical epoch tolerance required')
    pairs = []
    for a in unique_peaks(first, fs):
        for b in unique_peaks(second, fs):
            difference = float(wrap(b['epoch']-a['epoch'], fs/750))
            if abs(difference) <= tolerance:
                pairs.append(dict(first=a, second=b, epoch_difference_samples=difference,
                    epoch_difference_s=difference/fs,
                    differential_cfo_hz=float(wrap(b['cfo']-a['cfo'])),
                    minimum_margin=min(a['margin'], b['margin'])))
    return pairs


def circular_line(times, values, *, tolerance_hz=150., maximum_rate_hz_s=60., seed=25019):
    """Bounded deterministic RANSAC proposal; no inference-position input."""
    t, y = np.asarray(times, float), np.asarray(values, float)
    if t.shape != y.shape or t.ndim != 1 or len(t) < 3 or not np.isfinite(np.r_[t,y]).all():
        raise ValueError('three finite paired measurements required')
    center = float(np.median(t))
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(512):
        a, b = rng.choice(len(t), 2, replace=False)
        if abs(t[b]-t[a]) < 1:
            continue
        rate = float(wrap(y[b]-y[a]) / (t[b]-t[a]))
        if abs(rate) > maximum_rate_hz_s:
            continue
        offset = float(wrap(y[a]-rate*(t[a]-center)))
        residual = wrap(y-offset-rate*(t-center))
        active = abs(residual) < tolerance_hz
        score = (int(active.sum()), -float(np.minimum(abs(residual),tolerance_hz).sum()))
        if best is None or score > best[0]:
            best = (score, offset, rate, active)
    if best is None:
        return None
    _, offset, rate, active = best
    for _ in range(5):
        if active.sum() < 3:
            break
        target = y + np.round((offset+rate*(t-center)-y)/PERIOD)*PERIOD
        design = np.column_stack((np.ones(len(t)),t-center))
        offset, rate = np.linalg.lstsq(design[active],target[active],rcond=None)[0]
        residual = wrap(y-offset-rate*(t-center))
        changed = abs(residual) < tolerance_hz
        if np.array_equal(changed,active):
            break
        active = changed
    return dict(reference_time_s=center, offset_hz=float(wrap(offset)), rate_hz_s=float(rate),
        inliers=active, residual_hz=wrap(y-offset-rate*(t-center)),
        tolerance_hz=tolerance_hz, maximum_rate_hz_s=maximum_rate_hz_s)
