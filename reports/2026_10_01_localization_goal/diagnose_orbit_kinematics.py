"""Position-derivative versus authoritative-velocity audit, without altering orbits."""
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from physics import LIGHT_KM_S, enu_state_ecef_km, helmert_contrasts, hermite_interpolate
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def position_derivative(times, positions, query, width=5):
    """Differentiate a local position-only Lagrange polynomial in scaled time."""
    times, positions = np.asarray(times), np.asarray(positions)
    if (width < 3 or width % 2 != 1 or len(times) < width
            or positions.shape != (len(times), 3)
            or not times[width//2] <= query <= times[-width//2]
            or not np.allclose(np.diff(times), times[1]-times[0])):
        raise ValueError('invalid uniform table or query support')
    spacing = times[1]-times[0]
    left = int(np.searchsorted(times, query, side='right'))-1-width//2
    left = min(max(left, 0), len(times)-width)
    u = (query-times[left])/spacing
    derivative = np.zeros(3)
    for j in range(width):
        others = [k for k in range(width) if k != j]
        weight = sum(np.prod([u-k for k in others if k != m]) for m in others)
        weight /= np.prod([j-k for k in others])*spacing
        # Subtract a common position to reduce cancellation; derivative of a
        # constant is zero analytically. This keeps translated frames stable.
        derivative += weight*(positions[left+j]-positions[left])
    return derivative


def main():
    start = time.monotonic()
    frozen = HERE/'regression-v1-freeze.json'
    assert digest(frozen) == frozen.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(frozen.read_text())['source_sha256'])
    rows = []
    for unit in ['DS9-F001', 'DS10-F056', 'DS11-F001']:
        parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
        assert digest(parent_path) == json.loads(parent_path.with_suffix('.seal.json').read_text())[
            'prediction_sha256']
        parent = json.loads(parent_path.read_text())
        scan, height, ports = prepare(unit)
        assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
        assert [list(p.observation_ids) for p in ports] == parent['observations']
        state = np.asarray(parent['best']['mean'])
        assigned = [int(np.argmax(p.score_all(state))) for p in ports]
        labels = sorted({i for p, i in zip(ports, assigned, strict=True) if i < p.candidate_count})
        columns = np.array([0, 1, 2, 3, 4, *(5+i for i in labels)])
        information = np.diag(np.r_[0., 0., 1., np.full(len(columns)-3, 4.)])
        rhs = np.zeros(len(columns))
        receiver = enu_state_ecef_km(*state[:2], height(*state[:2]),
                                    scan.config.prior_center_lat_deg,
                                    scan.config.prior_center_lon_deg)
        tracks = []
        for port, index in zip(ports, assigned, strict=True):
            if index == port.candidate_count:
                continue
            indices = [port.track.observation_ids.index(i) for i in port.observation_ids]
            times = port.track.times_s[indices]+state[2]+state[5+index]
            contrasts = helmert_contrasts(port.track.receiver_indices[indices])
            delta_hz, refinement_hz, velocity_norm = [], [], []
            for query in times:
                p, v, _ = hermite_interpolate(scan.bank.times_s,
                                             scan.bank.positions_ecef_km[index],
                                             scan.bank.velocities_ecef_km_s[index], float(query))
                d5 = position_derivative(scan.bank.times_s, scan.bank.positions_ecef_km[index],
                                         float(query), 5)
                d7 = position_derivative(scan.bank.times_s, scan.bank.positions_ecef_km[index],
                                         float(query), 7)
                line = p-receiver
                line /= np.linalg.norm(line)
                factor = scan.config.doppler_sign*scan.config.reference_frequency_hz/LIGHT_KM_S
                delta_hz.append(float(factor*line@(d7-v)))
                refinement_hz.append(float(factor*line@(d7-d5)))
                velocity_norm.append(float(1000*np.linalg.norm(d7-v)))
            delta = contrasts@delta_hz
            refinement = contrasts@refinement_hz
            prediction = port.predict_selected(state, index)
            residual = port.observation-prediction.mean
            solved = np.linalg.solve(prediction.covariance, residual)
            weight = (4+len(residual))/(4+residual@solved)
            jacobian = prediction.jacobian[:, columns]
            information += weight*jacobian.T@np.linalg.solve(prediction.covariance, jacobian)
            rhs -= weight*jacobian.T@np.linalg.solve(prediction.covariance, delta)
            white_delta = np.linalg.solve(np.linalg.cholesky(prediction.covariance), delta)
            tracks.append(dict(
                norad=int(scan.bank.norad_ids[index]),
                maximum_velocity_difference_m_s=max(velocity_norm),
                maximum_uncontrasted_doppler_difference_hz=max(map(abs, delta_hz)),
                maximum_contrast_difference_hz=float(np.max(np.abs(delta))),
                whitened_contrast_difference_norm=float(np.linalg.norm(white_delta)),
                maximum_contrast_refinement_hz=float(np.max(np.abs(refinement)))))
        shift = np.linalg.solve(information, rhs)
        rows.append(dict(unit=unit, parent_sha256=digest(parent_path), tracks=tracks,
                         approximate_irls_position_shift_m=float(1000*np.linalg.norm(shift[:2])),
                         approximate_irls_position_step_m=(1000*shift[:2]).tolist(),
                         maximum_velocity_difference_m_s=max(
                             t['maximum_velocity_difference_m_s'] for t in tracks),
                         maximum_contrast_difference_hz=max(
                             t['maximum_contrast_difference_hz'] for t in tracks),
                         maximum_contrast_refinement_hz=max(
                             t['maximum_contrast_refinement_hz'] for t in tracks),
                         maximum_white_contrast_difference=max(
                             t['whitened_contrast_difference_norm'] for t in tracks)))
    result = dict(
        source_sha256=digest(__file__), original_freeze_sha256=digest(frozen),
        seconds=time.monotonic()-start, rows=rows,
        source='https://help.agi.com/stk/12.10.0/SubSystems/dataProviders/Content/html/'
        'dataProviders/Relative_Motion.htm',
        qualification='Position-only5/7-knot polynomial differentiation compared with existing '
        'authoritative SGP4 ECEF velocities. SGP4 velocity need not equal position derivative; '
        'difference is not by itself a defect or a justified correction. Doppler differences use '
        'unchanged position/line of sight and within-RX contrasts. IRLS displacement is a local '
        'sensitivity estimate, not a nonlinear refit, measured error or accuracy claim. No GPS.')
    output = HERE/'orbit-kinematics-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps([{k: v for k, v in r.items() if k != 'tracks'} for r in rows], indent=2))


if __name__ == '__main__':
    main()
