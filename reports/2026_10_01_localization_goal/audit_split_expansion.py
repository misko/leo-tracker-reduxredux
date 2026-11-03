"""Audit training-only cold fits and candidate disjointness without GPS."""
import json
from pathlib import Path

import numpy as np
from evaluate_regression import qualification
from regression_batch import digest, verify_sources
from run_split_expansion import prepare

HERE = Path(__file__).resolve().parent


def main():
    directory = HERE/'split-expansion-fit-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    rows = []
    for unit in frozen['units']:
        path = directory/(unit+'.json')
        launch = json.loads(path.with_suffix('.launch.json').read_text())
        errors, receipt = [], {}
        try:
            assert launch['freeze_sha256'] == digest(freeze)
            assert digest(path) == launch['receipt_sha256']
            seal = json.loads(path.with_suffix('.seal.json').read_text())
            assert digest(path) == seal['prediction_sha256']
            receipt = json.loads(path.read_text())
            for filename, expected in receipt['source_sha256'].items():
                assert frozen['source_sha256'][filename] == expected
            assert receipt['unit_id'] == unit and receipt['arm'] == 'hard'
            source_path = HERE/'source-split-expansion-v1'/(unit+'.json')
            assert digest(source_path) == source_path.with_suffix('.sha256').read_text().strip()
            source = json.loads(source_path.read_text())
            train = set(source['training_source_groups'])
            check = set(source['checking_source_groups'])
            assert train.isdisjoint(check)
            assert all(set(t['source_group_ids']) <= train for t in source['training_tracks'])
            assert all(p['source_group_id'] in check for p in source['checking_points'])
            check_ids = {p['candidate_id'] for p in source['checking_points']}
            assert all(check_ids.isdisjoint(t['candidate_ids']) for t in source['training_tracks'])
            scan, height, ports = prepare(unit)
            assert scan.inputs == receipt['inputs']
            verify_sources(scan.inputs)
            assert height.input_bindings == receipt['height']
            parent_path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
            assert digest(parent_path) == source['parent_sha256']
            parent = json.loads(parent_path.read_text())
            assert receipt['config'] == parent['config']
            assert receipt['height'] == parent['height']
            assert receipt['observations'] == [list(p.observation_ids) for p in ports]
            ids = [v for p in ports for v in p.observation_ids]
            assert len(ids) == len(set(ids))
            state = np.asarray(receipt['best']['mean'])
            precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
            objective = .5*(precision*state)@state-sum(np.max(p.score_all(state)) for p in ports)
            assert abs(objective-receipt['best']['objectives'][-1]) < 1e-6
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append(type(error).__name__+': '+str(error))
        failures = qualification(receipt, launch, not errors)
        rows.append(dict(unit=unit, accepted=not failures, failures=failures, audit_errors=errors,
                         retained_training_tracks=len(receipt.get('observations', [])),
                         runtime_s=launch['elapsed_seconds'], cpu_s=receipt.get('cpu_seconds'),
                         receipt_sha256=launch['receipt_sha256']))
    result = dict(planned=12, accepted=sum(r['accepted'] for r in rows), rows=rows,
                  freeze_sha256=digest(freeze), auditor_sha256=digest(__file__),
                  qualification='Training-only inference audit, no geographic scoring or model '
                  'selection. Checking candidate sets sealed before fit. Preprocessing times '
                  'are recorded separately in source exports; runtime includes fresh localization '
                  'candidate acquisition and fitting, matching frozen regression timing scope.')
    output = HERE/'split-expansion-fit-v1-audit.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
