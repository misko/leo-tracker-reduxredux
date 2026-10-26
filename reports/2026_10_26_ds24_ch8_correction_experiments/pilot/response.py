"""Small fixed-anchor channel-response experiment using tested pilot tools.

This is within-window prediction conditional on full-window acquisition. It is
not a cross-fitted detector, a false-positive calibration, or an admission rule.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from frequency_selective_pilot import ChannelPilotWorkspace
from dsx01_pilot_clock import FrameClock, WindowClock, minimize_profile
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, CYCLIC_PREFIX_DURATION_S


def paired_interval(values, denominator, seed=630):
    """Descriptive frame bootstrap, preserving the two symbol directions."""
    values = np.asarray(values, float)
    denominator = np.asarray(denominator, float)
    if len(values) < 4:
        raise ValueError('at least four paired frame losses required')
    rng = np.random.default_rng(seed)
    index = rng.integers(len(values), size=(2000, len(values)))
    ratios = values[index].sum(axis=1)/denominator[index].sum(axis=1)
    return [float(x) for x in np.quantile(ratios, [.025, .975])]


def predict(workspace, *, flat=False, control=False):
    """Per-frame LS gains/DC trained on one parity and applied to the other."""
    columns = workspace.columns(control=control)
    if flat:
        columns = columns.sum(axis=1, keepdims=True)
    design = np.column_stack((columns, np.ones(len(workspace.y))))
    frames = []
    for k in range(len(workspace.frames)):
        squared_error = energy = 0.
        directions = []
        for train_name, test_name in [('symbol_even', 'symbol_odd'), ('symbol_odd', 'symbol_even')]:
            train = workspace.indices(k, 0., 0., train_name)
            test = workspace.indices(k, 0., 0., test_name)
            coefficient = np.linalg.lstsq(design[train], workspace.y[train], rcond=1e-8)[0]
            residual = workspace.y[test] - design[test]@coefficient
            error = float(np.vdot(residual, residual).real)
            raw = workspace.y[test]
            raw_energy = float(np.vdot(raw, raw).real)
            squared_error += error
            energy += raw_energy
            directions.append(dict(train=train_name, heldout_samples=len(test), squared_error=error,
                                   raw_energy=raw_energy))
        frames.append(dict(frame=k, squared_error=squared_error, raw_energy=energy, directions=directions))
    return dict(frames=frames, squared_error=sum(x['squared_error'] for x in frames),
                raw_energy=sum(x['raw_energy'] for x in frames),
                complex_coefficients_per_frame=2 if flat else 9,
                channel_parameters_real_per_frame=2 if flat else 16,
                DC_parameters_real_per_frame=2)


def compare(samples, rate, edge, epoch, acquired_cfo):
    """Hold original fractional epoch and finalized CFO exactly fixed."""
    samples = np.asarray(samples, complex)
    t = np.arange(len(samples))/rate
    values = samples*np.exp(-2j*np.pi*acquired_cfo*t)
    p = ChannelPilotWorkspace(values, rate, edge, epoch, rotation_cache_bytes=0)
    results = {}
    for name, flat, control in [('flat', True, False), ('per_tone', False, False),
                                ('wrong_sequence_flat', True, True), ('wrong_sequence_per_tone', False, True)]:
        results[name] = predict(p, flat=flat, control=control)
        results[name]['in_sample_explained_fraction'] = float(p.evaluate([0.], flat=flat, control=control)[0])
    flat, tone, wrong = [results[k] for k in ('flat', 'per_tone', 'wrong_sequence_per_tone')]
    improvement = 1-tone['squared_error']/flat['squared_error']
    gain_frames = [a['squared_error']-b['squared_error'] for a,b in zip(flat['frames'], tone['frames'])]
    baseline = [a['squared_error'] for a in flat['frames']]
    exact_frames = [a['squared_error']-b['squared_error'] for a,b in zip(wrong['frames'], tone['frames'])]
    wrong_baseline = [a['squared_error'] for a in wrong['frames']]
    interval = paired_interval(gain_frames, baseline)
    sequence_interval = paired_interval(exact_frames, wrong_baseline)
    return dict(models=results, held_symbol_relative_SSE_improvement=improvement,
        descriptive_frame_bootstrap_95_interval=interval,
        correct_over_wrong_relative_SSE_improvement=1-tone['squared_error']/wrong['squared_error'],
        correct_over_wrong_descriptive_frame_bootstrap_95_interval=sequence_interval,
        response_predictive_support=bool(interval[0] > 0 and sequence_interval[0] > 0),
        exact_CFO_anchor_hz=float(acquired_cfo), exact_epoch_anchor_samples=float(epoch),
        CFO_fitted=False, timing_fitted=False, received_symbol_rate_fitted=False,
        original_full_window_acquisition_exposure=True,
        validation='two directions of even/odd within-window symbols; channel/DC trained independently per frame',
        bootstrap_caveat='frame resampling is descriptive; frames may be dependent; this is not calibrated coverage')


def _parity_frame(frame, parity, rate, epoch):
    """Use the existing guarded FrameClock geometry with a symbol split."""
    start = int(np.ceil(epoch + 2*OFDM_SYMBOL_DURATION_S*rate))
    stop = int(np.floor(epoch + 302*OFDM_SYMBOL_DURATION_S*rate))
    index = np.arange(start, stop)
    times = (index-epoch)/rate
    symbols = np.floor(times/OFDM_SYMBOL_DURATION_S+1e-10).astype(int)
    local = times-symbols*OFDM_SYMBOL_DURATION_S
    mask = (symbols >= 2)&(symbols <= 301)
    mask &= local >= CYCLIC_PREFIX_DURATION_S+.6/rate
    mask &= local <= OFDM_SYMBOL_DURATION_S-.6/rate
    symbols = symbols[mask]
    if len(symbols) != len(frame.values):
        raise ValueError('existing guarded frame geometry changed')
    choose = symbols%2 == parity
    sub = copy.copy(frame)
    for field in ('time', 'basis', 'values'):
        setattr(sub, field, getattr(frame, field)[choose])
    sub.phase_derivative = frame.phase_derivative[:, choose]
    sub.energy = float(np.vdot(sub.values, sub.values).real)
    return sub


def _fit_clock(frames, symbol_rate):
    model = WindowClock(frames)
    dimensions = 2 if symbol_rate else 1
    def objective(x):
        full = np.zeros(2)
        full[:dimensions] = x
        value, gradient = model.objective(full)
        return value, gradient[:dimensions]
    # One start only: original CFO and zero received-symbol-rate term.
    fitted = minimize_profile(objective, np.zeros(dimensions), [(-.24, .24), (-2., 2.)][:dimensions])
    x, loss, calls, converged = fitted
    full = np.zeros(2)
    full[:dimensions] = x
    return dict(coordinates=full.tolist(), residual_cfo_hz=float(full[0]*500),
                received_symbol_rate_ppm=float(full[1]*50), normalized_residual=loss,
                evaluations=calls, converged=converged,
                boundary=bool(abs(full[0]) >= .23999 or (symbol_rate and abs(full[1]) >= 1.9999)))


def _clock_prediction(train, test, fit):
    x = np.asarray(fit['coordinates'])
    errors = []
    for first, other in zip(train, test):
        design = first.basis*np.exp(np.einsum('p,pnk->nk', x, first.phase_derivative))
        gains = np.linalg.lstsq(design, first.values, rcond=1e-8)[0]
        held = other.basis*np.exp(np.einsum('p,pnk->nk', x, other.phase_derivative))
        residual = other.values-held@gains
        errors.append(float(np.vdot(residual, residual).real))
    return errors


def symbol_rate_diagnostic(samples, rate, edge, epoch, acquired_cfo):
    """Separate guarded received-clock model; never combined with admission."""
    frames = []
    origins = []
    k = 0
    while epoch+(k+1)*rate/750+16 < len(samples):
        origin = epoch+k*rate/750
        if origin >= 0:
            frames.append(FrameClock(samples, rate, origin, acquired_cfo, edge))
            origins.append(origin)
        k += 1
    splits = [[_parity_frame(f, parity, rate, o) for f,o in zip(frames, origins)] for parity in (0, 1)]
    models = {}
    for name, enabled in [('per_tone_no_rate', False), ('per_tone_received_rate', True)]:
        fits = [_fit_clock(splits[parity], enabled) for parity in (0, 1)]
        errors = [_clock_prediction(splits[parity], splits[1-parity], fits[parity]) for parity in (0, 1)]
        models[name] = dict(fits=fits, frame_squared_errors=np.sum(errors, axis=0).tolist(),
                            held_symbol_squared_error=float(np.sum(errors)))
    first, second = models.values()
    a = np.asarray(first['frame_squared_errors']); b = np.asarray(second['frame_squared_errors'])
    return dict(models=models, held_symbol_relative_SSE_improvement=1-b.sum()/a.sum(),
                descriptive_frame_bootstrap_95_interval=paired_interval(a-b, a),
                independent_frame_channel=True, DC_model=False,
                carrier_residual_bound_hz=120, received_rate_bound_ppm=100,
                original_timing_fixed=True, original_full_window_acquisition_exposure=True,
                received_rate_is_not_transmitter_clock=True,
                separate_guarded_geometry_from_primary_response_comparison=True)


def synthetic(seed, mode='channel', noise_sigma=.7, rate=2500000., size=25000):
    rng = np.random.default_rng(seed)
    epoch = 23.2
    p = ChannelPilotWorkspace(np.zeros(size, complex), rate, 'lower', epoch, rotation_cache_bytes=0)
    columns = p.columns(control=mode == 'wrong_sequence')
    samples = (rng.normal(size=size)+1j*rng.normal(size=size))*noise_sigma/np.sqrt(2)
    for ix in p.frames:
        gains = (rng.normal(size=8)+1j*rng.normal(size=8))/np.sqrt(2)
        if mode == 'flat':
            gains[:] = np.exp(1j*rng.uniform(-np.pi,np.pi))
        if mode != 'noise':
            samples[ix] += columns[ix]@gains + (.1+.2j)*rng.normal()
    cfo = 12345.25
    samples *= np.exp(2j*np.pi*cfo*np.arange(size)/rate)
    return samples, rate, 'lower', epoch, cfo
