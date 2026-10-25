"""Copy previously published control metrics; evaluate no new geography."""

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = Path('/srv/bulk/leo/research/ds24-movement-policy-r01')
CASES = ('DS24-0095', 'DS24-0087')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def main():
    position_path = PREVIOUS/'evaluation/recovery_positions.csv'
    trial_path = PREVIOUS/'evaluation/recovery_trial_positions.csv'
    seal = read(PREVIOUS/'evaluation/seal.json')['files']
    for path in (position_path, trial_path):
        assert sha(path) == seal[str(path.relative_to(PREVIOUS))]
    with position_path.open() as stream:
        positions = list(csv.DictReader(stream))
    with trial_path.open() as stream:
        trials = list(csv.DictReader(stream))
    rows, sources = [], {str(path): sha(path) for path in (position_path, trial_path)}
    for case in CASES:
        support_path = PREVIOUS/'recovery/eligibility02'/case/'result.json'
        support = read(support_path)['selected']
        assert support is not None and support['accepted'] and support['paired_valid']
        sources[str(support_path)] = sha(support_path)
        for arm in ('c0', 'fitted_c'):
            base = next(r for r in positions if r['case'] == case and r['arm'] == arm and r['policy'] == 'baseline')
            active = next(r for r in positions if r['case'] == case and r['arm'] == arm and r['policy'] == 'support_active_incumbent_control')
            invalid = next(r for r in trials if r['case'] == case and r['arm'] == arm and r['branch'] == 'graph'
                and int(r['trial_index']) == support['source_graph_trial'] and r['version'] == 'ordinary')
            assert invalid['final_trial_accepted'] == invalid['final_trial_paired_valid'] == 'False'
            assert invalid['constrained_refinement_attempted'] == 'False'
            for name, source, qualified, role in [
                ('saved_baseline', base, True, 'original curved + original predictive'),
                ('saved_ordinary_shape_present_graph', invalid, False, 'new target in curved calibration'),
                ('saved_phase_only_support_control', active, True, 'new target in curved calibration')]:
                target = 0 if name == 'saved_baseline' else support['added_curved_points']
                original_curved, original_predictive = int(base['curved_points']), int(base['predictive_points'])
                rows.append(dict(case=case, arm=arm, saved_control=name,
                    original_qualification_passed=qualified,
                    qualification_note='INVALID: original one-owner support rule' if not qualified else 'saved original control qualification',
                    evidence_role=role, original_parent_curved_points=original_curved,
                    target_curved_points=target, original_predictive_points=original_predictive,
                    likelihood_points=original_curved+target+original_predictive,
                    error_km=float(source['error_km']), curved_RMS_hz=float(source['curved_RMS_hz']),
                    association_counts_not_inferred_from_likelihood=True,
                    metric_source=str(trial_path if name == 'saved_ordinary_shape_present_graph' else position_path)))
    assert len(rows) == 12
    out = HERE/'saved_control_reference.csv'
    with out.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    receipt = dict(status='passed', no_new_geographic_evaluation=True, no_position_fits=True,
        previously_published_control_rows=12, source_sha256=sha(Path(__file__)), inputs=sources,
        table_sha256=sha(out), limitation='Saved graph control is INVALID. New predictive factors change evidence role and use a conditioned phase prior; comparison to these saved controls does not isolate shape covariance.')
    with (HERE/'saved_control_reference_receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
