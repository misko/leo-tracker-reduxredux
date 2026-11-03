"""Audit conditional reference profiles and decompose their objective gaps."""
import json
from pathlib import Path

import numpy as np

from fixed_reference_nuisance import ConditionalObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
directory = HERE/'fixed-reference-nuisance-v1'
freeze = directory/'sources.json'
assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
frozen = json.loads(freeze.read_text())
verify_sources(frozen['source_sha256'])
rows, receipts = [], {}
for unit, arm in frozen['pairs']:
    path = directory/(unit+'-'+arm+'.json')
    launch = json.loads(path.with_suffix('.launch.json').read_text())
    errors, receipt, numeric_decrement, gradient_error = [], {}, None, None
    try:
        assert launch['returncode'] == 0 and launch['within_budget'] and not launch['timed_out']
        assert launch['freeze_sha256'] == digest(freeze)
        assert digest(path) == launch['receipt_sha256']
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        receipt = json.loads(path.read_text())
        assert receipt['converged'], receipt['reason']
        model = ConditionalObjective(unit, arm)
        assert receipt['parent_sha256'] == digest(model.path)
        assert receipt['assignments'] == model.assignments
        assert receipt['initial'] == model.initial.tolist()
        assert receipt['height'] == model.parent['height'] and receipt['inputs'] == model.parent['inputs']
        state = np.asarray(receipt['state'])
        assert np.array_equal(state[:2], model.initial[:2])
        assert model.support(state[model.columns])
        assert np.allclose(model.metric(), receipt['metric'], atol=1e-10, rtol=1e-10)
        metric = np.asarray(receipt['metric'])
        value, gradient = model.evaluate(state[model.columns])
        assert abs(value-receipt['final_objective']) < 1e-7
        assert abs(value-receipt['objectives'][-1]) < 1e-7
        assert np.all(np.diff(receipt['objectives']) <= 1e-9)
        assert gradient@np.linalg.solve(metric, gradient) <= 1e-6
        finite = []
        point = state[model.columns]
        for direction in np.eye(len(point))*.0005:
            a = model.evaluate(point+direction, gradient=False)[0]
            b = model.evaluate(point-direction, gradient=False)[0]
            finite.append((a-b)/.001)
        finite = np.asarray(finite)
        gradient_error = float(np.max(abs(finite-gradient)))
        numeric_decrement = float(finite@np.linalg.solve(metric, finite))
        assert gradient_error < .005 and numeric_decrement < 1e-5
        decomposition = model.decompose(state)
        assert decomposition == receipt['decomposition']
        summed = decomposition['shared_prior']+decomposition['unused_epoch_prior']
        summed += sum(g['observation_nll']+g['epoch_prior'] for g in decomposition['groups'].values())
        assert abs(summed-value) < 1e-7
        if arm == 'control':
            assert abs(value-model.parent['best']['objectives'][-1]) < 1e-6
        receipts[(unit, arm)] = receipt
    except (AssertionError, OSError, ValueError, KeyError) as error:
        errors.append(type(error).__name__+': '+str(error))
    rows.append(dict(unit=unit, arm=arm, valid=not errors, failures=errors,
        objective=receipt.get('final_objective'), reason=receipt.get('reason'),
        maximum_gradient_error=gradient_error, numeric_decrement_squared=numeric_decrement,
        runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_s')))
comparisons = []
for unit in dict.fromkeys(u for u, _ in frozen['pairs']):
    if any((unit, arm) not in receipts for arm in ['control', 'reference']):
        continue
    control, reference = receipts[(unit, 'control')], receipts[(unit, 'reference')]
    old, new = control['decomposition'], reference['decomposition']
    assert old['groups'].keys() == new['groups'].keys()
    groups = []
    for identity, group in new['groups'].items():
        baseline = old['groups'][identity]
        assert baseline['tracks'] == group['tracks']
        observation = group['observation_nll']-baseline['observation_nll']
        epoch = group['epoch_prior']-baseline['epoch_prior']
        groups.append(dict(identity=identity, tracks=group['tracks'], observation_gap=observation,
                           epoch_prior_gap=epoch, total_gap=observation+epoch))
    shared_gap = new['shared_prior']-old['shared_prior']
    unused_gap = new['unused_epoch_prior']-old['unused_epoch_prior']
    total_gap = reference['final_objective']-control['final_objective']
    assert abs(sum(g['total_gap'] for g in groups)+shared_gap+unused_gap-total_gap) < 1e-7
    positive = sorted([g for g in groups if g['total_gap'] > 0], key=lambda g: -g['total_gap'])
    positive_sum = sum(g['total_gap'] for g in positive)
    comparisons.append(dict(unit=unit, objective_gap=total_gap, shared_prior_gap=shared_gap,
        unused_epoch_prior_gap=unused_gap, groups=groups,
        positive_group_count=len(positive), positive_group_sum=positive_sum,
        top3_positive_group_fraction=sum(g['total_gap'] for g in positive[:3])/positive_sum if positive_sum else None,
        largest_positive_groups=positive[:3]))
result = dict(rows=rows, comparisons=comparisons, planned=len(rows), valid=sum(r['valid'] for r in rows),
    freeze_sha256=digest(freeze), auditor_sha256=digest(__file__),
    qualification='Explicit reference-informed offline diagnostic. Fixed original hard identities '
    'and one inherited nuisance start, locally stationary only. Objective gaps and group '
    'concentrations cannot prove wrong identities, global reference optimum, or a correction '
    'rule. No localization error/acceptance metric or deployment model is produced.')
output = HERE/'fixed-reference-nuisance-v1-audit.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(dict(planned=result['planned'], valid=result['valid'], rows=rows,
    comparisons=[{k: v for k, v in r.items() if k != 'groups'} for r in comparisons]), indent=2))
