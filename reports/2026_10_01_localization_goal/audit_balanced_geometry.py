"""Group score and local information diagnostics; no reference reads."""
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from balanced_group_objective import BalancedGroupObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def information_at(model, state, coefficients):
    columns = model.columns
    prior = np.diag(model.precision[columns])
    parts, scores, counts = {}, {}, Counter()
    for port, label, coefficient in zip(model.ports, model.assignments, coefficients, strict=True):
        if label == port.candidate_count:
            continue
        key = str(model.scan.bank.norad_ids[label])
        counts[key] += 1
        scores[key] = scores.get(key, 0.)-float(port.score_selected(state, label))
        prediction = port.predict_selected(state, label)
        residual = port.observation-prediction.mean
        solved = np.linalg.solve(prediction.covariance, residual)
        weight = (4+len(residual))/(4+residual@solved)
        j = prediction.jacobian[:, columns]
        part = coefficient*weight*j.T@np.linalg.solve(prediction.covariance, j)
        parts[key] = parts.get(key, np.zeros_like(prior))+part
    matrix = prior+sum(parts.values())
    d = np.vstack([np.eye(2), -np.linalg.solve(matrix[2:, 2:], matrix[2:, :2])])
    schur = d.T@matrix@d
    inverse = np.linalg.inv(schur)
    shares = {k: float(np.trace(inverse@(d.T@p@d))) for k, p in parts.items()}
    prior_share = float(np.trace(inverse@(d.T@prior@d)))
    assert abs(sum(shares.values())+prior_share-2) < 1e-7
    assert min(shares.values()) >= -1e-9 and prior_share >= -1e-9
    total = sum(shares.values())
    eig = np.linalg.eigvalsh(schur)
    return dict(information=schur.tolist(), eigenvalues=eig.tolist(),
        major_curvature_axis_m=float(1000/np.sqrt(eig[0])), condition=float(eig[-1]/eig[0]),
        prior_information_share=prior_share/2,
        singleton_signal_information_fraction=sum(v for k, v in shares.items() if counts[k] == 1)/total,
        effective_information_groups=total**2/sum(v*v for v in shares.values()),
        groups=[dict(identity=k, track_count=counts[k], observation_nll=scores[k],
                     signal_information_fraction=shares[k]/total) for k in parts])


def main():
    start = time.monotonic()
    selection = HERE/'split-expansion-fit-v1/sources.json'
    assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
    sources = {str(Path(__file__)): digest(__file__)}
    inputs = {str(selection): digest(selection)}
    rows = []
    for unit in json.loads(selection.read_text())['units']:
        directory = HERE/('balanced-group-v1' if unit in ['DS9-F025', 'DS10-F028', 'DS11-F018']
                          else 'balanced-group-expansion-v1')
        freeze = directory/'sources.json'
        assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
        frozen = json.loads(freeze.read_text())
        verify_sources(frozen['source_sha256'])
        sources.update(frozen['source_sha256'])
        path = directory/f'{unit}-balanced.json'
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        assert launch['receipt_sha256'] == digest(path) and launch['returncode'] == 0
        receipt = json.loads(path.read_text())
        assert receipt['converged']
        model = BalancedGroupObjective(unit, 'balanced')
        assert receipt['parent_sha256'] == digest(model.path)
        assert receipt['assignments'] == model.assignments
        assert receipt['weights'] == model.weights.tolist()
        inputs[str(path)] = digest(path)
        old = model.initial
        new = np.asarray(receipt['state'])
        baseline = information_at(model, old, np.ones(len(model.ports)))
        reweighted = information_at(model, old, model.weights)
        final = information_at(model, new, model.weights)
        lower = np.linalg.cholesky(np.asarray(baseline['information']))
        ratio = np.linalg.solve(lower, reweighted['information'])
        ratio = np.linalg.solve(lower, ratio.T).T
        old_groups = {g['identity']: g for g in baseline['groups']}
        for group in final['groups']:
            group['unweighted_nll_change'] = group['observation_nll']-old_groups[group['identity']]['observation_nll']
        rows.append(dict(unit=unit, baseline=baseline, reweighted_at_baseline=reweighted,
            balanced_endpoint=final, fixed_state_information_ratios=np.linalg.eigvalsh(ratio).tolist(),
            singleton_count=sum(g['track_count'] == 1 for g in baseline['groups']),
            groups=len(baseline['groups']), maximum_track_weight=float(max(model.weights))))
    result = dict(rows=rows, seconds=time.monotonic()-start, source_sha256=sources, inputs=inputs,
        qualification='Reference-free IRLS local-information and fixed-label score decomposition. '
        'Curvature axes are not calibrated confidence radii. Effective groups summarize information '
        'concentration, not independent sample size. No geographic selector or new fit.')
    output = HERE/'balanced-geometry-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(seconds=result['seconds'], rows=[dict(unit=r['unit'],
        ratios=r['fixed_state_information_ratios'], singleton_count=r['singleton_count'],
        old_singleton=r['baseline']['singleton_signal_information_fraction'],
        new_singleton=r['balanced_endpoint']['singleton_signal_information_fraction'],
        old_axis_m=r['baseline']['major_curvature_axis_m'],
        new_axis_m=r['balanced_endpoint']['major_curvature_axis_m']) for r in rows]), indent=2))


if __name__ == '__main__':
    main()
