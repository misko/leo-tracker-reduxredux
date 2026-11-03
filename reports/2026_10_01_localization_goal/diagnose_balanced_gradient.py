"""Inspect sealed failed endpoint without fitting, GPS, or acceptance changes."""
import json
from pathlib import Path

import numpy as np

from balanced_group_objective import BalancedGroupObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
directory = HERE/'balanced-group-regression-v1'
freeze = directory/'sources.json'
assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
verify_sources(json.loads(freeze.read_text())['source_sha256'])
path = directory/'DS11-F031-balanced.json'
assert digest(path) == path.with_suffix('.sha256').read_text().strip()
receipt = json.loads(path.read_text())
model = BalancedGroupObjective('DS11-F031', 'balanced')
assert receipt['parent_sha256'] == digest(model.path)
assert receipt['weights'] == model.weights.tolist()
state = np.asarray(receipt['state'])
point = state[model.columns]
value, gradient = model.evaluate(point)
assert abs(value-receipt['final_objective']) < 1e-7
step = .0005
finite = np.array([(model.evaluate(point+d, False)[0]-model.evaluate(point-d, False)[0])/(2*step)
                   for d in np.eye(len(point))*step])
worst = int(np.argmax(abs(finite-gradient)))
column = int(model.columns[worst])
rows = []
for h in [.005, .001, .0005, .0001, .00005, .00001, .000001]:
    minus, plus = state.copy(), state.copy()
    minus[column] -= h
    plus[column] += h
    below = model.evaluate(minus[model.columns], False)[0]
    above = model.evaluate(plus[model.columns], False)[0]
    pieces = []
    for k, (port, label, coefficient) in enumerate(zip(model.ports, model.assignments, model.weights, strict=True)):
        a, b = port.score_selected(minus, label), port.score_selected(plus, label)
        g = 0.
        if label < port.candidate_count:
            prediction = port.predict_selected(state, label)
            r = port.observation-prediction.mean
            solved = np.linalg.solve(prediction.covariance, r)
            weight = (4+len(r))/(4+r@solved)
            g = float(-coefficient*weight*prediction.jacobian[:, column]@solved)
        numeric = float(-coefficient*(b-a)/(2*h))
        if abs(numeric-g) > .001:
            scores_a, scores_b = port.score_all(minus), port.score_all(plus)
            visible_a = np.isfinite(scores_a[:-1])
            visible_b = np.isfinite(scores_b[:-1])
            changed = np.flatnonzero(visible_a != visible_b)
            pieces.append(dict(track=k, assigned_clutter=label == port.candidate_count,
                analytic=g, numeric=numeric, score_minus=float(a), score_plus=float(b),
                visible_minus=int(visible_a.sum()), visible_plus=int(visible_b.sum()),
                changed_norad_ids=[int(model.scan.bank.norad_ids[i]) for i in changed]))
    rows.append(dict(step=h, analytic=float(gradient[worst]), numeric=(above-below)/(2*h),
        left_slope=(value-below)/h, right_slope=(above-value)/h,
        delta_minus=below-value, delta_plus=above-value, discrepant_tracks=pieces))
result = dict(unit='DS11-F031', full_state_column=column, initial_check_max_error=float(max(abs(finite-gradient))),
    rows=rows, source_sha256={str(Path(__file__)): digest(__file__)},
    inputs={str(path): digest(path), str(freeze): digest(freeze)},
    qualification='Sealed endpoint diagnostic only. No reference coordinates, refit, restart, '
    'threshold change or retroactive acceptance. Visibility inferred from finite branch scores.')
output = HERE/'balanced-gradient-diagnosis-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(result, indent=2))
