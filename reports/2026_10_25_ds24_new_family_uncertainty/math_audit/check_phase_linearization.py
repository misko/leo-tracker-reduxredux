"""Stage-0 direct phase/Doppler and physical-mode check; no position fits."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import t

import recovery as r
from build_dsx01_orbit_modes import build_modes
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from prototype_dsx01_continuous_position import latlon

HERE = Path(__file__).resolve().parent
CASES = ('DS24-0095', 'DS24-0087')


def write_new(path, data):
    def encode(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(type(value).__name__)
    with Path(path).open('x') as stream:
        json.dump(data, stream, default=encode, indent=2, allow_nan=False)
        stream.write('\n')


def rms(v):
    return float(np.sqrt(np.mean(np.asarray(v)**2)))


def one(case):
    d = r.context(case)
    selected_path = r.HERE/'eligibility02'/case/'result.json'
    selected = r.read(selected_path)['selected']
    target = selected['additions'][0]
    j = int(target['candidate_index'])
    i = next(i for i, track in enumerate(d['scan'].tracks) if track['key'] == target['component'])
    track = d['scan'].tracks[i]
    times = np.asarray(track['times'])
    q = float(track['rf_hz'])/11.5e9
    mu, sigma = float(d['all_means'][j]), float(d['widths'][j])
    nu = d['model']['nu']
    if nu is None or nu <= 2:
        raise ValueError('this audit expects the frozen finite-variance Student phase law')
    scale = sigma*np.sqrt((nu-2)/nu)
    lost_mass = float(t.cdf((-15-mu)/scale, nu) + t.sf((15-mu)/scale, nu))
    bank = dict(time_s=d['scan'].sky['time_s'], position_km=d['scan'].sky['position_km'][[j]],
        velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    modes, metadata = build_modes(d['scan'], [j], [j], 'physical')
    meta = d['scan'].fixed_window_noise
    native_sigma = np.array([meta['per_observation_noise_sigma_hz'][oid] if meta['extra_parameter_BIC_gain']>0
        else d['scan'].radio_sigma_hz for oid in track['observation_ids']])
    offsets = [('minus2sd', -2*sigma), ('minus1sd', -sigma), ('plus1sd', sigma), ('plus2sd', 2*sigma)]
    offsets += [(f'unconditioned_quantile_{prob}', float(scale*t.ppf(prob, nu))) for prob in (.025, .975)]
    evaluations = []
    for arm in r.ARMS:
        for endpoint, saved in [('baseline', d['arms'][arm]), ('support', selected['arms'][arm])]:
            x = np.asarray(saved['endpoint_east_north_km'])
            coordinates = latlon(x)
            def frequency(phase):
                return q*phase_frequency_grid(bank, times, *coordinates, phase_seconds=phase)[0][0]
            nominal = frequency(mu)
            derivative = (frequency(mu+.01)-frequency(mu-.01))/.02
            design = np.column_stack((np.ones(len(times)), derivative))
            basis, _ = np.linalg.qr(design/native_sigma[:, None])
            def project(values):
                a = np.asarray(values)/native_sigma[:, None] if np.asarray(values).ndim == 2 else np.asarray(values)/native_sigma
                return a-basis@(basis.T@a)
            shape = q*paired_frequency_modes(bank, modes, times, np.zeros(len(times), int), np.array([mu]), *coordinates)
            projected_shape = project(shape)
            row = dict(case=case, arm=arm, endpoint=endpoint, position_east_north_km=x,
                target_points=len(times), phase_mean_s=mu, phase_marginal_sd_s=sigma, phase_nu=nu,
                physical_shape_prior=metadata[j], shape_RMS_marginal_hz=rms(np.sqrt(np.sum(shape**2, axis=1))),
                projected_shape_RMS_marginal_hz=rms(np.sqrt(np.sum((projected_shape*native_sigma[:, None])**2, axis=1))),
                projected_shape_RMS_native_sigma_units=rms(np.sqrt(np.sum(projected_shape**2, axis=1))), offsets=[])
            for name, offset in offsets:
                actual_phase = mu+offset
                if not -15 <= actual_phase <= 15:
                    row['offsets'].append(dict(name=name, phase_s=actual_phase, outside_declared_fit_domain=True))
                    continue
                exact = frequency(actual_phase)
                error = exact-nominal-derivative*offset
                projected = project(error)
                row['offsets'].append(dict(name=name, phase_s=actual_phase, offset_s=offset,
                    raw_RMS_error_hz=rms(error), raw_max_error_hz=float(np.max(abs(error))),
                    projected_RMS_error_hz=rms(projected*native_sigma),
                    projected_max_error_hz=float(np.max(abs(projected*native_sigma))),
                    projected_RMS_error_native_sigma_units=rms(projected)))
            evaluations.append(row)
    return dict(case=case, target=target, track_index=i, points=len(times),
        target_ids_sha256=hashlib.sha256(json.dumps(track['observation_ids'], separators=(',', ':')).encode()).hexdigest(),
        prior_probability_outside_15s_domain=lost_mass, phase_prior_note='unit-variance Student marginal is unbounded; truncation would be a new explicit prior-conditioning choice',
        original_selected_binding=dict(path=str(selected_path), sha256=r.sha(selected_path)), evaluations=evaluations)


if __name__ == '__main__':
    result = dict(stage='pre_fit_phase_linearization', new_position_fits=0, GPS_used=False,
        projection='native-sigma weighted removal of target constant and local causal-phase derivative',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), cases=[one(c) for c in CASES])
    write_new(HERE/'phase_linearization.json', result)
    for case in result['cases']:
        print(case['case'], 'SD', case['evaluations'][0]['phase_marginal_sd_s'],
            'prior_mass_outside_domain', case['prior_probability_outside_15s_domain'])
        for row in case['evaluations']:
            print(row['arm'], row['endpoint'], 'projected_shape_RMS_Hz', row['projected_shape_RMS_marginal_hz'],
                'projected_errors', [(o['name'], o.get('projected_RMS_error_hz')) for o in row['offsets']])
