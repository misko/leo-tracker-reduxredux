"""Independent artifact consistency and unchanged-source checks for publication."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    checked = 0
    for source, digest in read(ROOT/'cohort/provenance.json')['source_files_sha256'].items():
        assert sha(Path(source)) == digest, source
        checked += 1
    mechanism = ROOT/'mechanism'
    replays = []
    for group in ('all', 'ch1_4', 'ch5_8'):
        for case in ('DS24-0015', 'DS24-0019'):
            d = read(mechanism/f'{group}_{case}.json')
            assert sha(Path(d['source'])) == d['source_sha256']
            assert set(d['arms']) == {'c0', 'fitted_c'}
            for arm in d['arms'].values():
                assert abs(arm['replay_objective_delta']) < 1e-3
                assert arm['derivative_step_relative_change'] < 1e-5
                replays.append(arm['replay_objective_delta'])
    evaluation = read(mechanism/'evaluation.json')
    assert len(evaluation['restarts']) == 8
    assert all(r['displacement_m'] < .4 and not r['failed_curved'] and not r['failed_predictive']
               for r in evaluation['restarts'])
    convergence = [arm['history'][-1]['phase_change_s']
                   for path in list(mechanism.glob('ablate_*.json')) + list(mechanism.glob('restart_DS24*.json'))
                   for arm in read(path)['arms'].values()]
    assert len(convergence) == 16 and max(convergence) <= .01
    assert len(list(mechanism.glob('ablate_*.json'))) == 4
    for path in mechanism.glob('ablate_*.json'):
        d = read(path)
        assert d['same_deletion_mask_and_budgets_in_both_c_arms']
        assert d['original_nuisance_design_support_and_other_priors_preserved']
        assert d['arms']['c0']['active_points'] == d['arms']['fitted_c']['active_points']
        assert d['arms']['c0']['predictive_points'] == d['arms']['fitted_c']['predictive_points']
    links = []
    for target in re.findall(r'\]\(([^)]+)\)', (ROOT/'README.md').read_text()):
        if '://' not in target:
            assert (ROOT/target.split('#')[0]).is_file(), target
            links.append(target)
    result = dict(passed=True, input_hashes_verified=checked,
                  mechanism_replays=len(replays), maximum_absolute_replay_difference=max(map(abs, replays)),
                  matched_restarts=8, maximum_restart_displacement_m=max(r['displacement_m'] for r in evaluation['restarts']),
                  matched_deletion_pairs=4, report_links_checked=len(links),
                  maximum_final_phase_change_s=max(convergence),
                  validation_does_not_establish_physical_truth_or_algorithm_improvement=True)
    (ROOT/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
