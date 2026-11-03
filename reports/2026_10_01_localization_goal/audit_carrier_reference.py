"""Reference-free local sensitivity to nominal pilot/tuner distinction."""
import json
import time
from pathlib import Path

import numpy as np

from acquisition_dot import prepare
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
started = time.monotonic()
selection = HERE/'split-expansion-fit-v1/sources.json'
assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
sources = {str(Path(__file__)): digest(__file__)}
inputs = {str(selection): digest(selection)}
rows = []
for unit in json.loads(selection.read_text())['units']:
    path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256']
    parent = json.loads(path.read_text())
    verify_sources(parent['source_sha256'])
    verify_sources(parent['inputs'])
    sources.update(parent['source_sha256'])
    inputs.update(parent['inputs'])
    inputs[str(path)] = digest(path)
    scan, height, ports = prepare(unit)
    assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
    assert [list(p.observation_ids) for p in ports] == parent['observations']
    evidence_path = HERE.parent/'2026_09_30_gaussian_sum_64_scan/evidence'/f'{unit}.json'
    evidence = json.loads(evidence_path.read_text())
    metadata = {r['track_id']: r for r in evidence['tracks']}
    state = np.asarray(parent['best']['mean'])
    assignments = [int(np.argmax(p.score_all(state))) for p in ports]
    epochs = sorted({5+i for p, i in zip(ports, assignments, strict=True) if i < p.candidate_count})
    columns = [0, 1, 2, 3, 4, *epochs]
    information = np.diag(np.r_[0., 0., 1., np.full(len(columns)-3, 4.)])
    rhs = np.zeros(len(columns))
    tracks = []
    for (track_id, track), port, identity in zip(scan.tracks, ports, assignments, strict=True):
        meta = metadata[track_id]
        assert meta['rf_hz'] == track.rf_hz
        channel = meta['channel']
        assert channel in range(1, 9)
        # Read from pinned deployment contract; infer the nearest nominal edge,
        # since exported track metadata omits the explicit edge field.
        carriers = np.array([10709687500., 10940312500.])+(channel-1)*250000000.
        edge = int(np.argmin(abs(carriers-track.rf_hz)))
        carrier = float(carriers[edge])
        difference = carrier-track.rf_hz
        assert abs(difference) < 1000000  # require unambiguous nearby nominal edge
        epsilon = difference/track.rf_hz
        row = dict(track_id=track_id, channel=channel, rf_hz=track.rf_hz,
                   inferred_nominal_edge=['lower', 'upper'][edge], nominal_carrier_hz=carrier,
                   difference_hz=difference, fractional_difference=epsilon,
                   assigned=identity < port.candidate_count)
        if identity < port.candidate_count:
            prediction = port.predict_selected(state, identity)
            likelihood = port.likelihood
            drift = likelihood.contrasts@(
                state[3+likelihood.receiver_indices]*likelihood.drift_scale*likelihood.centered_times)
            orbital_mean = prediction.mean-drift
            correction = epsilon*orbital_mean
            residual = port.observation-prediction.mean
            solved = np.linalg.solve(prediction.covariance, residual)
            weight = (4+len(residual))/(4+residual@solved)
            jacobian = prediction.jacobian[:, columns]
            precision_j = np.linalg.solve(prediction.covariance, jacobian)
            information += weight*jacobian.T@precision_j
            # Fit perturbation for a positive correction to predicted means.
            rhs -= weight*precision_j.T@correction
            row['maximum_contrast_correction_hz'] = float(np.max(abs(correction)))
        tracks.append(row)
    step = np.linalg.solve(information, rhs)
    assert np.linalg.norm(information@step-rhs) < 1e-9*max(1., np.linalg.norm(rhs))
    assert np.allclose(np.linalg.solve(information, -rhs), -step, atol=1e-12)
    rows.append(dict(unit=unit, tracks=tracks, position_step_km=step[:2].tolist(),
        predicted_position_shift_m=float(1000*np.linalg.norm(step[:2])),
        maximum_carrier_difference_hz=max(abs(r['difference_hz']) for r in tracks),
        maximum_contrast_correction_hz=max(r.get('maximum_contrast_correction_hz', 0) for r in tracks)))
result = dict(rows=rows, seconds=time.monotonic()-started, source_sha256=sources, inputs=inputs,
    nominal_frequency_contract='/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/'
        '.venv/lib/python3.14/site-packages/leo/contracts/starlink_frequency.py',
    qualification='Fixed-state IRLS mean-perturbation sensitivity, not nonlinear refit or geographic error. '
    'Nearest published edge inferred from channel and tuned RF, not measured carrier or hardware '
    'calibration. Cannot bound physical oscillator, transmitter, or within-band effective-frequency '
    'errors. Weights, identities and Jacobians fixed; priors retained. No reference coordinates read.')
output = HERE/'carrier-reference-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(dict(seconds=result['seconds'], rows=[{k: v for k, v in r.items() if k != 'tracks'} for r in rows]), indent=2))
