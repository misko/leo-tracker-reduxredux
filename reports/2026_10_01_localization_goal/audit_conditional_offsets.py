"""Conditional offset uncertainty under an explicit raw Student-t extension."""
import json
import time
from pathlib import Path

import numpy as np

from candidate_joint_expansion_adapter import CandidateJointObjective, LIGHT_KM_S
from physics import _noise_covariance
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def conditional_offset(n, contrast_quadratic, offset_precision, nu=4.):
    """Flat offset prior, raw n-variate t_nu scale C; return df, scale, SD."""
    if n < 2 or contrast_quadratic < 0 or offset_precision <= 0 or nu <= 0:
        raise ValueError('invalid conditional offset inputs')
    df = nu+n-1
    scale2 = (nu+contrast_quadratic)/(df*offset_precision)
    return df, np.sqrt(scale2), np.sqrt(scale2*df/(df-2)) if df > 2 else np.inf


def main():
    started = time.monotonic()
    freeze = HERE/'split-expansion-fit-v1/sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    sources = dict(frozen['source_sha256'])
    for name in ['audit_conditional_offsets.py', 'candidate_joint_expansion_adapter.py',
                 'candidate_spatial_expansion_adapter.py']:
        sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources)
    calibration_path = HERE/'candidate-density-transfer-v1.json'
    assert digest(calibration_path) == calibration_path.with_suffix('.sha256').read_text().strip()
    parameters = {f['target_dataset']: f['fitted'] for f in json.loads(calibration_path.read_text())['folds']}
    rows, inputs = [], {str(calibration_path): digest(calibration_path)}
    for unit in frozen['units']:
        model = CandidateJointObjective(unit)
        b, state = model.base, model.base.initial
        verify_sources(b.parent['inputs'])
        inputs[str(b.parent_path)] = digest(b.parent_path)
        source_path = HERE/'source-split-expansion-v1'/(unit+'.json')
        assert digest(source_path) == source_path.with_suffix('.sha256').read_text().strip()
        inputs[str(source_path)] = digest(source_path)
        receiver = model.receiver(state[:2])
        factor = b.scan.config.doppler_sign*b.scan.config.reference_frequency_hz/LIGHT_KM_S
        group_for_slot = {slot: j for j, slots in enumerate(b.group_slots) for slot in slots}
        active = [(k, port, index) for k, (port, index) in enumerate(zip(b.ports, b.assignments, strict=True))
                  if index < port.candidate_count]
        offset = 0
        for (track, port, index), (query, prepared_index, rx, n, weights, measured, center) in zip(
                active, model.prepared, strict=True):
            assert index == prepared_index
            positions, velocities = query._orbit_states_per_satellite([state[2]+state[5+index]])
            line = positions[0]-receiver
            line /= np.linalg.norm(line, axis=1, keepdims=True)
            raw = factor*np.sum(velocities[0]*line, axis=1)
            raw += state[3+rx]*query.drift_scale*(query.times-center)
            times = query.times[:n]
            covariance = _noise_covariance(times, b.scan.config)
            ones = np.ones(n)
            precision = float(ones@np.linalg.solve(covariance, ones))
            mean_offset = float(weights@(measured-raw[:n]))
            residual = measured-raw[:n]-mean_offset
            quadratic = float(residual@np.linalg.solve(covariance, residual))
            prediction = port.predict_selected(state, index)
            contrast = port.observation-prediction.mean
            contrast_q = float(contrast@np.linalg.solve(prediction.covariance, contrast))
            assert abs(quadratic-contrast_q) < 1e-6
            df, scale, sd = conditional_offset(n, quadratic, precision)
            checking = []
            for local in range(len(query.times)-n):
                group_index = group_for_slot[offset+local]
                group = b.groups[group_index]
                if len(b.group_slots[group_index]) != 1 or not len(group['candidates']):
                    continue
                residuals = (group['candidates']-raw[n+local]-mean_offset+group['period']/2
                             ) % group['period']-group['period']/2
                nearest = float(residuals[np.argmin(abs(residuals))])
                checking.append((group['time'], nearest))
            offset += len(query.times)-n
            checking.sort()
            errors = np.array([v for _, v in checking])
            signs = errors > 0
            count, positive = len(errors), int(signs.sum())
            expected = ((positive*(positive-1)+(count-positive)*(count-positive-1))
                        /count if count >= 2 else 0.)
            calibrated_scale = parameters[unit.split('-')[0]]['scale_hz']
            rows.append(dict(unit=unit, track=track, satellite_index=index, n=n,
                contrast_quadratic=quadratic, contrast_q_parity=abs(quadratic-contrast_q),
                posterior_df=df, posterior_scale_hz=float(scale), posterior_sd_hz=float(sd),
                calibrated_residual_scale_hz=calibrated_scale,
                offset_sd_to_calibrated_scale=float(sd/calibrated_scale),
                checking_groups=count, checking_median_residual_hz=float(np.median(errors)) if count else None,
                adjacent_pairs=max(count-1, 0),
                adjacent_same_sign=int(np.sum(signs[1:] == signs[:-1])),
                shuffled_expected_same_sign=float(expected),
                checking_time_gaps_s=np.diff([t for t, _ in checking]).tolist()))
    verify_sources(sources)
    verify_sources(inputs)
    result = dict(rows=rows, source_sha256=sources, input_sha256=inputs,
        tracks=len(rows), median_offset_sd_hz=float(np.median([r['posterior_sd_hz'] for r in rows])),
        p90_offset_sd_hz=float(np.percentile([r['posterior_sd_hz'] for r in rows], 90)),
        offset_sd_exceeds_calibrated_scale=sum(r['offset_sd_to_calibrated_scale'] > 1 for r in rows),
        checking_groups=sum(r['checking_groups'] for r in rows),
        adjacent_pairs=sum(r['adjacent_pairs'] for r in rows),
        adjacent_same_sign=sum(r['adjacent_same_sign'] for r in rows),
        shuffled_expected_same_sign=sum(r['shuffled_expected_same_sign'] for r in rows),
        seconds=time.monotonic()-started,
        qualification='Assumes raw Student-t4 extension with covariance from existing raw noise '
        'model and flat per-track offset prior, conditional on fitted state and identity. '
        'Contrast-only likelihood alone does not identify common-mode variance. Candidate '
        'scale was calibrated on total residuals, not independent measurement noise; adding '
        'this variance to it would risk double counting. Nearest-peak residuals are selected '
        'diagnostics, not verified signal labels or absolute errors. Adjacent pairs span '
        'successive eligible groups within a track with no maximum gap; shuffling conditions '
        'on each track sign count. No iid significance claim. No GPS or new fits.')
    output = HERE/'conditional-offset-audit-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'source_sha256', 'input_sha256']}, indent=2))


if __name__ == '__main__':
    main()
