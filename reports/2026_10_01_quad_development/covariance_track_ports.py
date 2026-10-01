"""Nested sixteen-point ports for a fixed covariance-shape ablation."""
from dataclasses import replace
import numpy as np
from denser_window_inputs import prepare_denser_window
from denser_track_ports import build_ports
from trace_matched_noise import matched_white_variance
from adapter import TrackPort
from leo.analysis.localization_windows import WindowTrackPort


def build_covariance_ports(scan, height, arm):
    if arm not in ('tau10', 'matched_white'):
        raise ValueError('Unknown covariance arm')
    dense, selection = build_ports(scan, height, 16)
    ports, parameters = [], []
    for old in dense:
        times = old.likelihood.times
        raw = scan.config.white_noise_hz**2*np.eye(len(times))+scan.config.correlated_noise_hz**2*np.exp(-abs(times[:, None]-times[None, :])/10.)
        if arm == 'tau10':
            config = replace(old.config, correlation_time_s=10.)
        else:
            variance = matched_white_variance(raw, old.likelihood.contrasts)
            config = replace(old.config, white_noise_hz=float(np.sqrt(variance)), correlated_noise_hz=0., correlation_time_s=10.)
        port = TrackPort(old.track, scan.bank, scan.layout, config, height)
        assert port.observation_ids == old.observation_ids
        ports.append(port)
        parameters.append(dict(white_noise_hz=config.white_noise_hz,
            correlated_noise_hz=config.correlated_noise_hz, correlation_time_s=config.correlation_time_s))
    return ports, dict(selection=selection, covariance_parameters=parameters)


def prepare_covariance_window(unit, arm):
    original, _ = prepare_denser_window(unit, 16)
    binding, scans, columns, precision, _ = original
    ports, details = [], []
    for (scan, height, _), indices in zip(scans, columns):
        local, description = build_covariance_ports(scan, height, arm)
        ports.extend(WindowTrackPort(p, indices, len(precision)) for p in local)
        details.append(dict(scan=scan.unit_id, **description))
    return (binding, scans, columns, precision, ports), details
