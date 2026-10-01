"""Seal full-objective choices using accepted same-target receipts only."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed
from target_objective_policy import select

HERE = Path(__file__).resolve().parent


def main():
    output = HERE/'target-objective-decisions-v1.json'
    if output.exists(): raise FileExistsError(output)
    inputs = {}

    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value

    manifest = read(HERE/'window-candidate-manifest-v1.json')
    for key in ('sources', 'inputs', 'frozen_sources_and_inputs'):
        for name, expected in manifest[key].items(): assert digest(name) == expected, name
    rows = []
    for block in manifest['blocks']:
        receipts, objectives = [], []
        for candidate in block['candidates']:
            path = Path(candidate['receipt_path']); receipt = read(path)
            assert digest(path) == candidate['receipt_sha256']
            assert receipt['status'] == 'converged_local_mode' and receipt['best']['converged']
            assert receipt['best']['mean'][:2] == candidate['point_km']
            audit = read(Path(candidate['audit_path']))
            matches = [r for r in audit['rows'] if r['unit'] == candidate['unit']]
            assert len(matches) == 1 and matches[0]['accepted'] and matches[0]['receipt_sha256'] == digest(path)
            objective = float(receipt['best']['objectives'][-1]); assert np.isfinite(objective)
            objectives.append(objective); receipts.append(receipt)
        for target in block['targets']:
            decision = select(block['candidates'], objectives, target)
            baseline = receipts[decision['baseline']]
            for index in decision['eligible']:
                receipt = receipts[index]
                for key in ('binding', 'inputs', 'observations', 'precision', 'columns', 'height', 'model'):
                    assert receipt[key] == baseline[key], (target['unit_id'], key)
                def config(r):
                    return {k: v for k, v in r['config'].items() if k not in ('seed_limit', 'max_iterations')}
                assert config(receipt) == config(baseline)
            rows.append(dict(unit=target['unit_id'], block=block['block'], dataset=block['dataset'], size=target['size'],
                baseline=block['candidates'][decision['baseline']]['id'],
                selected=block['candidates'][decision['selected']]['id'],
                eligible=[block['candidates'][i]['id'] for i in decision['eligible']],
                objectives={block['candidates'][i]['id']: objectives[i] for i in decision['eligible']},
                objective_improvement=objectives[decision['baseline']]-objectives[decision['selected']]))
    assert len(rows) == 112
    sources = {str(HERE/n): digest(HERE/n) for n in ('select_target_objectives.py', 'target_objective_policy.py',
        'window_candidate_policy.py', 'test_target_objective_policy.py', 'TARGET_OBJECTIVE_PLAN.md')}
    result = dict(rows=rows, inputs=inputs, sources=sources,
        qualification='Separate post-result no-refit arm. Only accepted same-target states with identical model/data bindings. '
        'Minimize full audited objective, including each candidate nuisance state; first fit wins1e-6ties. '
        'No error fields or reference coordinates accessed by the selection code.')
    with output.open('x') as stream: json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(targets=len(rows), changed=sum(r['selected'] != r['baseline'] for r in rows))))


if __name__ == '__main__': main()
