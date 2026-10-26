"""Truth-free research frequency proposal; public historical pilot ports only.

The Gaussian scale below follows an explicit complex-white-noise model. It is
an uncalibrated proposal for real recordings, never a production uncertainty.
"""
import dataclasses
import math
import numpy as np

from leo.analysis.starlink.fast_scan_fractional import fractional_take, fractional_take_bounds
from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
from leo.analysis.starlink.templates import qin_edge_pilot_frame, OFDM_SYMBOL_DURATION_S

VERSION = 'donor-complex-profile-v1'
GRID = np.arange(-3000., 3000.1, 25.)
GATE = .025
MAX_HYPOTHESES = 8


def correlations(samples, rate, edge, epoch, center):
    """Own symbol sufficient statistics; never borrow a private workspace.

    For x=A*t+CN(0,sigma2 I), c=<t,x> has complex variance sigma2*E.
    Orthogonal symbol residual energy/(n-1) estimates sigma2 independently
    of c at the fixed frequency under that model. Fractional interpolation,
    interference and wrong timing invalidate that independence on real RF.
    """
    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError('finite complex sample vector required')
    reference = np.asarray(qin_edge_pilot_frame(rate, edge), complex)
    symbols = np.arange(2, 66)
    starts = np.rint(symbols * rate * OFDM_SYMBOL_DURATION_S).astype(int)
    stops = np.rint((symbols + 1) * rate * OFDM_SYMBOL_DURATION_S).astype(int)
    count = stops - starts
    if np.any(count != count[0]) or count[0] < 2:
        raise ValueError('this frozen proposal requires uniform native symbol geometry')
    n = int(count[0]); relative = starts[:, None] + np.arange(n)
    template = reference[relative]; energy = np.sum(abs(template)**2, axis=1)
    integer = math.floor(epoch); fractional = epoch - integer
    left, right = fractional_take_bounds(fractional)
    frames = []; times = []; residual = []; starts_used = []
    for frame in range(int(len(values) / (rate/750.)) + 1):
        frame_start = integer + round(frame * rate/750.)
        absolute = frame_start + relative + fractional
        if absolute.min() < left:
            continue
        if absolute.max() >= len(values) - right:
            break
        received = values[absolute.astype(int)] if fractional == 0 else fractional_take(values, absolute)
        corrected = received * np.exp(-2j*np.pi*center*absolute/rate)
        c = np.sum(np.conj(template)*corrected, axis=1)
        frames.append(c)
        times.append(np.mean(absolute, axis=1)/rate)
        residual.append(np.sum(abs(corrected)**2, axis=1) - abs(c)**2/energy)
        starts_used.append([int(math.floor(absolute.min()))-left,
                            int(math.ceil(absolute.max()))+right+1])
    if len(frames) < 2:
        raise ValueError('fewer than two complete GLRT64 frames')
    c = np.asarray(frames); times = np.asarray(times)
    residual = np.maximum(np.asarray(residual), 0.)
    sigma2 = float(np.sum(residual) / (residual.size * (n-1)))
    if sigma2 <= 0 or not math.isfinite(sigma2):
        raise ValueError('noise scale must be positive')
    # Per-symbol frame-origin phase is absorbed in the unknown complex A_frame.
    return c, times-times[:, :1], energy, sigma2, dict(
        frames=len(frames), symbols_per_frame=64, native_samples_per_symbol=n,
        complete_frame_sample_envelopes=starts_used,
        mean_symbol_residual_complex_variance=sigma2,
        per_frame_residual_variance=(np.mean(residual, axis=1)/(n-1)).tolist(),
        variance_convention='E|complex noise|^2; each real component sigma2/2',
        phase_approximation='residual CFO rotation at each symbol midpoint',
        maximum_within_symbol_phase_error_rad=float(np.pi*3000*(n-1)/rate))


def profile(c, times, energy, sigma2, prediction_sigma, elapsed):
    """Profile frame amplitudes and combine one fixed robust prediction prior.

    Profile log likelihood = sum_f |sum_s c_fs exp(-i2pi df t_fs)|^2 /
    (sigma2 sum_s E_s). This is not the normalized GLRT margin. Prediction
    prior is .9 Gaussian + .1 uniform on the frozen +/-3kHz domain. Its
    width includes packet uncertainty, 250Hz discrepancy and 400Hz/s drift.
    """
    rotation = np.exp(-2j*np.pi*GRID[:, None, None]*times[None, :, :])
    sums = np.sum(c[None, :, :]*rotation, axis=2)
    loglike = np.sum(abs(sums)**2, axis=1)/(sigma2*np.sum(energy))
    sigma = math.sqrt(prediction_sigma**2+250.**2+(400.*elapsed)**2)
    gaussian = np.exp(-.5*(GRID/sigma)**2)/(sigma*np.sqrt(2*np.pi))
    prior = .9*gaussian + .1/6000.
    score = loglike + np.log(prior)
    w = np.exp(score-np.max(score)); w /= np.sum(w)
    cdf = np.cumsum(w)
    quantiles = np.interp([.025, .5, .975], cdf, GRID)
    modes = np.flatnonzero((score >= np.r_[-np.inf, score[:-1]]) &
                           (score >= np.r_[score[1:], -np.inf]))
    modes = sorted(modes, key=lambda i: (-score[i], abs(GRID[i]), GRID[i]))
    # All grid local maxima are retained, including low-weight alternatives.
    return dict(map_offset_hz=float(GRID[np.argmax(score)]),
                median_offset_hz=float(quantiles[1]),
                conditional_95_interval_offsets_hz=[float(quantiles[0]), float(quantiles[2])],
                conditional_sd_hz=float(np.sqrt(np.sum(w*(GRID-np.sum(w*GRID))**2))),
                prediction_prior_sigma_hz=sigma,
                modes=[dict(offset_hz=float(GRID[i]), relative_log_score=float(score[i]-score.max()),
                            grid_mass=float(w[i])) for i in modes],
                grid_offsets_hz=GRID.tolist(), conditional_grid_weights=w.tolist(),
                relative_log_likelihood=(loglike-loglike.max()).tolist(),
                scores_are_physical_RF_likelihood=False,
                uncertainty_weights_qualified=False,
                scale_status='complex-white-noise model proposal; RF scale uncalibrated')


def estimate(later_samples, sample_rate_hz, edge, packet):
    """Estimate using later support and earlier measurements only; no truth API.

    Hypothesis alternatives and modes share the target support. They are never
    independent observations, and no donor information is a fresh data point.
    """
    if sample_rate_hz != 10_000_000:
        raise ValueError('frozen native rate is 10MHz')
    target = packet['target_support']
    if target['stop_counter']-target['start_counter'] != len(later_samples):
        raise ValueError('target sample support length mismatch')
    hypotheses = packet['hypotheses']
    if len(hypotheses) > MAX_HYPOTHESES:
        raise ValueError('donor hypothesis cap exceeded')
    out = dict(schema=VERSION, prediction_id=packet['prediction_id'], target_support=target,
               status='no_donor' if not hypotheses else 'complete', hypotheses=[],
               independent_new_observations=0, donor_information_is_conditioning=True,
               uncertainty_weights_qualified=False, no_truth_inputs=True)
    for h in hypotheses:
        center = float(h['predicted_cfo_hz']); epoch = float(h['epoch_samples'])
        sigma = float(h['prediction_sigma_hz']); dt = float(h['elapsed_s'])
        if not all(math.isfinite(x) for x in (center,epoch,sigma,dt)) or sigma < 0 or dt <= 0:
            raise ValueError('invalid prediction')
        if not h['donors']:
            raise ValueError('conditioning provenance absent')
        for donor in h['donors']:
            ds = donor['support']
            if ds['stop_counter'] > target['start_counter']:
                raise ValueError('donor support is not strictly earlier/disjoint')
        integer = math.floor(epoch)
        baseline = conditioned_glrt64_score(later_samples,sample_rate_hz,epoch_sample=integer,
            fractional_epoch_offset_samples=epoch-integer, acquired_cfo_hz=center,edge=edge)
        c,t,e,s2,stats = correlations(later_samples,sample_rate_hz,edge,epoch,center)
        proposed = profile(c,t,e,s2,sigma,dt)
        proposed['cfo_hz'] = center+proposed['map_offset_hz']
        proposed['conditional_95_interval_hz'] = [center+x for x in proposed['conditional_95_interval_offsets_hz']]
        for mode in proposed['modes']:
            mode['cfo_hz'] = center+mode['offset_hz']
        out['hypotheses'].append(dict(hypothesis_id=h['hypothesis_id'],donors=h['donors'],
            predicted_cfo_hz=center,prediction_sigma_hz=sigma,elapsed_s=dt,epoch_samples=epoch,
            gate_statistic=baseline.margin,passed_gate=bool(baseline.margin>=GATE),
            unchanged_later_bin=dataclasses.asdict(baseline),
            donor_carry=dict(cfo_hz=float(h['carry_cfo_hz']),
                status='copied earlier donor; no fresh independent Doppler measurement'),
            proposed=proposed,statistics=stats))
    out['primary'] = out['hypotheses'][0] if out['hypotheses'] else None
    out['any_passed_gate'] = any(h['passed_gate'] for h in out['hypotheses'])
    return out
