"""Symmetric 20-ms support scenarios at sealed states, not a new estimator."""
import copy
import json
import time
from pathlib import Path

import numpy as np

from acquisition_dot import prepare, LIGHT_KM_S, enu_state_ecef_km
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
start = time.monotonic()
selection = HERE/'split-expansion-fit-v1/sources.json'
assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
inputs = {str(selection): digest(selection)}
sources = {str(Path(__file__)): digest(__file__)}
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
    state = np.asarray(parent['best']['mean'])
    assignments = [int(np.argmax(p.score_all(state))) for p in ports]
    epochs = sorted({5+i for p, i in zip(ports, assignments, strict=True) if i < p.candidate_count})
    columns = [0, 1, 2, 3, 4, *epochs]
    information = np.diag(np.r_[0., 0., 1., np.full(len(columns)-3, 4.)])
    rhs = np.zeros((len(columns), 2))
    receiver = enu_state_ecef_km(*state[:2], height(*state[:2]),
        scan.config.prior_center_lat_deg, scan.config.prior_center_lon_deg)
    factor = scan.config.doppler_sign*scan.config.reference_frequency_hz/LIGHT_KM_S
    max_correction = np.zeros(2)
    refinement = 0.
    parity = 0.
    for port, identity in zip(ports, assignments, strict=True):
        if identity == port.candidate_count:
            continue
        prediction = port.predict_selected(state, identity)
        query = copy.copy(port.likelihood)
        query.bank = port._row_bank(identity)
        times = query.times.copy()

        def raw(offsets):
            query.times = (times[:, None]+np.asarray(offsets)[None, :]).ravel()
            position, velocity = query._orbit_states_per_satellite([state[2]+state[5+identity]])
            line = position[0]-receiver
            line /= np.linalg.norm(line, axis=1, keepdims=True)
            return (factor*np.sum(velocity[0]*line, axis=1)).reshape(len(times), -1)

        center = raw([0.])[:, 0]
        drift = (state[3+port.likelihood.receiver_indices]*port.likelihood.drift_scale
                 *port.likelihood.centered_times)
        parity = max(parity, float(np.max(abs(port.likelihood.contrasts@(center+drift)-prediction.mean))))
        means = []
        for order in [8, 16]:
            nodes, weights = np.polynomial.legendre.leggauss(order)
            means.append(raw(nodes*.01)@(weights/2))
        refinement = max(refinement, float(np.max(abs(means[0]-means[1]))))
        corrections = np.column_stack([means[1]-center, raw([-.01, .01]).mean(axis=1)-center])
        contrasts = port.likelihood.contrasts@corrections
        max_correction = np.maximum(max_correction, np.max(abs(contrasts), axis=0))
        residual = port.observation-prediction.mean
        solved = np.linalg.solve(prediction.covariance, residual)
        weight = (4+len(residual))/(4+residual@solved)
        j = prediction.jacobian[:, columns]
        precision_j = np.linalg.solve(prediction.covariance, j)
        information += weight*j.T@precision_j
        rhs -= weight*precision_j.T@contrasts
    assert parity < 1e-6 and refinement < 1e-6
    step = np.linalg.solve(information, rhs)
    assert np.linalg.norm(information@step-rhs) < 1e-9*max(1., np.linalg.norm(rhs))
    rows.append(dict(unit=unit, uniform_position_shift_m=float(1000*np.linalg.norm(step[:2, 0])),
        endpoints_position_shift_m=float(1000*np.linalg.norm(step[:2, 1])),
        maximum_contrast_correction_hz=max_correction.tolist(),
        quadrature_refinement_hz=refinement, center_prediction_parity_hz=parity))
result = dict(rows=rows, seconds=time.monotonic()-start, source_sha256=sources, inputs=inputs,
    qualification='Two prespecified symmetric20ms scenarios: uniform support and equal endpoint mass. '
    'Not actual per-candidate symbol weights, rigorous curvature bounds, receiver-clock calibration, '
    'or nonlinear fits. Fixed-state IRLS response only; unchanged priors/assignments. No GPS read.')
output = HERE/'window-average-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(dict(rows=rows, seconds=result['seconds']), indent=2))
