"""Fractional-frame and within-frame-frequency controls for phase coherence."""

from functools import lru_cache
import numpy as np
from ds23_conditional_pilot_components import component_geometry, component_segments
from ds23_differential_frame_phase import unique_frame_intersections, project_channel_phase
from probe_native_code_carrier import periodic_upsample, interpolate_periodic
from leo.analysis.starlink.templates import (OFDM_SYMBOL_DURATION_S, CYCLIC_PREFIX_DURATION_S,
    edge_frequencies_hz, qin_edge_pilot_symbols)


@lru_cache(maxsize=4)
def isolated_channel_waves(fs, edge):
    t = np.arange(int(np.ceil(fs/750)))/fs
    symbol = np.floor(t/OFDM_SYMBOL_DURATION_S).astype(int)
    keep = (symbol >= 2)&(symbol < 302)
    local = t[keep]-symbol[keep]*OFDM_SYMBOL_DURATION_S
    frame = np.zeros((len(t), 8), complex)
    frame[keep] = qin_edge_pilot_symbols(edge)[symbol[keep]-2]*np.exp(
        2j*np.pi*(local[:, None]-CYCLIC_PREFIX_DURATION_S)*edge_frequencies_hz(edge)[None])/np.sqrt(8)
    waves = tuple(periodic_upsample(frame[:, k], 32) for k in range(8))
    for array in waves: array.flags.writeable = False
    return waves


def fractional_geometry(samples, fs, edge, epoch, fit):
    geometry = component_geometry(samples, fs, edge, epoch, fit)
    n = np.arange(len(samples)); t = n/fs
    position = (n-epoch-fit['offset_samples'])*(1+fit['modulation_ppm']*1e-6)
    period = fs/750; local = position-np.floor(position/period)*period
    columns = np.column_stack([interpolate_periodic(w, local*32) for w in isolated_channel_waves(fs, edge)])
    rotation = np.exp(2j*np.pi*fit['CFO_hz']*(t-t.mean()))
    geometry['exact'] = columns*rotation[:, None]
    return geometry


def residualized_frequency_information(design, derivatives, noise_variance):
    x, d = np.asarray(design), np.asarray(derivatives)
    if x.ndim != 2 or d.shape != (len(x), 2) or not np.isfinite(noise_variance) or noise_variance <= 0:
        raise ValueError('supported complex channel and two frequency derivatives required')
    q, _ = np.linalg.qr(x, mode='reduced'); residual = d-q@(q.conj().T@d)
    return 2*np.real(residual.conj().T@residual)/noise_variance


def extract_fractional_phases(samples, fs, edge, first_epoch, first_fit, second_epoch, second_fit):
    y = np.asarray(samples, complex)
    a = fractional_geometry(y, fs, edge, first_epoch, first_fit)
    b = fractional_geometry(y, fs, edge, second_epoch, second_fit)
    segments = unique_frame_intersections(a, b, component_segments(a, b))
    if len(segments) < 10: raise ValueError('ten distinct matched transmitter frames required')
    design = np.column_stack((a['exact'], b['exact'], np.ones(len(y))))
    coefficients, covariance, times, information = [], [], [], np.zeros((2, 2))
    t = np.arange(len(y))/fs; centered = t-t.mean()
    for ix in segments:
        x = design[ix]; c, _, rank, _ = np.linalg.lstsq(x, y[ix], rcond=1e-8)
        if rank != 17: raise ValueError('fractional two-component design lost rank')
        residual = y[ix]-x@c; noise = float(np.vdot(residual, residual).real/(len(ix)-17))
        derivatives = 2j*np.pi*centered[ix, None]*np.column_stack((x[:, :8]@c[:8], x[:, 8:16]@c[8:16]))
        information += residualized_frequency_information(x, derivatives, noise)
        coefficients.append(c); covariance.append(noise*np.linalg.inv(x.conj().T@x)); times.append(float(t[ix].mean()))
    coefficients, covariance = np.array(coefficients), np.array(covariance); train = max(6, len(segments)*2//3)
    first = project_channel_phase(coefficients[:, :8], covariance[:, :8, :8], train)
    second = project_channel_phase(coefficients[:, 8:16], covariance[:, 8:16, 8:16], train)
    frequency_covariance = np.linalg.inv(information); contrast = np.array([1., -1.])
    return dict(time_s=np.array(times), first=first, second=second, train_frames=train,
        frame_pairs=[[int(a['frame'][s[0]]), int(b['frame'][s[0]])] for s in segments],
        within_frame_frequency_covariance_hz2=frequency_covariance,
        differential_frequency_sigma_proxy_hz=float(np.sqrt(contrast@frequency_covariance@contrast)),
        Gaussian_local_proxy_not_calibrated_RF_uncertainty=True)
