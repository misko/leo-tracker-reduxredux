"""Adapt the saved ALGO07 model to the existing calibrated orbit PNG layout."""
import numpy as np

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.predictive_track import receiver_design
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from leo.presentation.orbit_plot import OrbitCurve, OrbitLane, OrbitPeak


def calibrated_lanes(p, x, calculation, observations, owners, families, details):
    from prototype_dsx01_continuous_position import latlon

    times = np.linspace(0, 300, 1201)
    labels = np.zeros(len(times), int)
    coordinates = latlon(x)
    coefficient = calculation['coefficient']
    begin = p.hardware.shape[1] + p.smooth.shape[1]
    phases = p.state(x)['phases']
    curves = {}
    for local, j in enumerate(p.labels):
        n = int(p.scan.norads[j])
        if n not in set(owners.values()):
            continue
        bank = {k: v[[local]] if k != 'time_s' else v for k, v in p.sky.items()}
        reference = np.array([p.reference[local]])
        frequency, elevation = paired_phase_frequency(bank, times, labels, reference, *coordinates)
        derivative = (paired_phase_frequency(bank, times, labels, reference+.01, *coordinates)[0]
                      - paired_phase_frequency(bank, times, labels, reference-.01, *coordinates)[0])/.02
        # Same absolute-phase linearization and physical modes as the saved fit.
        frequency += derivative * (phases[j] - reference[0])
        if j in p.supported:
            modes = {k: v[3*local:3*local+3] if k != 'time_s' else v for k, v in p.mode_bank.items()}
            start = begin + len(p.labels) + 3*p.supported.index(j)
            orbital = calculation.get('predictive_orphan_orbit_coordinates', {}).get(j, coefficient[start:start+3])
            frequency += paired_frequency_modes(bank, modes, times, labels, reference, *coordinates) @ orbital
        curves[n] = np.where(elevation >= 0, frequency, np.nan)
    for f, detail in zip(families, details, strict=True):
        n = int(f.scan.norads[f.j])
        if n not in set(owners.values()):
            continue
        bank = {k: v[:1] if k != 'time_s' else v for k, v in f.bank.items()}
        modes = {k: v[:3] if k != 'time_s' else v for k, v in f.modes.items()}
        phase = np.array([detail['phase_map_s']])
        frequency, elevation = paired_phase_frequency(bank, times, labels, phase, *coordinates)
        frequency += paired_frequency_modes(bank, modes, times, labels, phase, *coordinates) @ detail['orbital_posterior_mean']
        curves[n] = np.where(elevation >= 0, frequency, np.nan)
    if set(curves) != set(owners.values()):
        raise ValueError('Full-scan orbit curves missing a published satellite')
    lanes = []
    for channel in range(1, 9):
        for receiver in (1, 2):
            points = [o for o in observations if o['receiver']==receiver and o['channel']==channel]
            rf = {o['actual_rf_hz'] for o in points}
            if len(rf) > 1:
                raise ValueError('One RF frame required per receiver/channel lane')
            # Empty lanes still retain the historical 16-lane layout.
            lane_rf = next(iter(rf), next((t['rf_hz'] for t in p.scan.tracks if t['channel']==channel), 11.5e9))
            t = np.array([o['time_s'] for o in points])
            correction = (receiver_design(t, lane_rf, receiver, channel, projected_receiver_basis(t),
                          fitted_c=p.fitted_c) @ coefficient[:begin]) if len(t) else []
            peaks = tuple(OrbitPeak(o['observation_id'], o['time_s'], o['measured_cfo_hz']-v,
                          str(owners[o['observation_id']]) if o['observation_id'] in owners else None)
                          for o, v in zip(points, correction, strict=True))
            orbital = tuple(OrbitCurve(str(n), tuple(times), tuple(v*lane_rf/11.5e9)) for n, v in sorted(curves.items()))
            lanes.append(OrbitLane(f'RX{receiver}', f'CH{channel}', peaks, orbital))
    return tuple(lanes)
