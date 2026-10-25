"""Regression audit of real augmented contexts; fixed positions only, no refits."""
import json
from pathlib import Path

import numpy as np
import recovery as r
import repair01 as repair

HERE = Path(__file__).resolve().parent


def main():
    protocol = repair.verify()
    assert protocol['graph_refits'] == protocol['new_candidates'] == protocol['new_rescues'] == 0
    assert protocol['global_budget_uses_original_wall_start'] is True
    assert protocol['coordinator_decision_sha256'] == r.sha(r.HERE.parent/'recovery_repair_decision.json')
    rows=[]
    for case in r.CASES:
        d=r.context(case)
        parent=r.read(r.HERE/case/'parent.json')
        assert sorted(d['original_protected']) == parent['original_protected'] == protocol['original_parent_protected'][case]
        order_path=r.HERE/case/'support/candidate_order.json'
        assert r.sha(order_path) == protocol['exact_original_candidate_order_sha256'][case]
        graph=r.read(r.HERE/case/'graph/result.json')
        assert r.sha(r.HERE/case/'graph/result.json') == protocol['graph_result_sha256'][case]
        order=r.read(order_path)['candidates']
        regenerated=r.eligible_support(d, graph['trials'])
        assert [trial['trial_index'] for trial, _ in regenerated] == [row['trial_index'] for row in order]
        prior_seconds=r.read(r.HERE/case/'support/result.json')['seconds']
        assert protocol['per_case_budget'][case]['original_support_seconds'] == prior_seconds
        assert protocol['per_case_budget'][case]['remaining_support_seconds'] == 240-prior_seconds
        for proposal in order:
            trial=next(row for row in graph['trials'] if row['trial_index'] == proposal['trial_index'])
            dd=dict(d, node=trial['node'], keep=np.asarray(trial['mask'],bool),
                means=np.asarray(trial['means']), entries=trial['entries'])
            for arm in r.ARMS:
                reference=trial['arms'][arm]['phase_reference']
                x=np.asarray(trial['arms'][arm]['endpoint_east_north_km'])
                expected=r.support.build(d, trial['node'], np.asarray(trial['mask'],bool), arm,
                    reference, np.asarray(trial['means']))
                actual=repair.corrected_build(dd, arm, reference, 'support')
                assert expected.supported == actual.supported
                assert expected.disabled_new_one_owner_orbit_families == actual.disabled_new_one_owner_orbit_families
                a,b=expected.calculate(x),actual.calculate(x)
                for key in ('features','coefficient_prior_precision','coefficient','noise_precision','negative_twice_elbo'):
                    np.testing.assert_array_equal(a[key], b[key])
                rows.append(dict(case=case,trial_index=trial['trial_index'],arm=arm,
                    original_protected=sorted(d['original_protected']),
                    augmented_protected=sorted(r.support.protected(dd)),
                    disabled_new_one_owner_orbit_families=actual.disabled_new_one_owner_orbit_families,
                    supported_families=[int(j) for j in actual.supported],
                    objective_difference=float(a['negative_twice_elbo']-b['negative_twice_elbo']),
                    fixed_graph_endpoint=x.tolist()))
    tests=HERE/'recovery_repair01_tests.txt'
    assert '2 passed' in tests.read_text()
    output=dict(all_passed=True, no_position_fits=True, GPS_used=False,
        protocol_sha256=r.sha(repair.OUT/'protocol.json'),source_sha256=r.sha(Path(__file__)),
        component_test_log_sha256=r.sha(tests),real_context_prechecks=rows,
        original_scientific_seal_sha256=r.sha(r.HERE/'scientific_seal.json'),
        original_graph_trials_and_failed_support_artifacts_preserved=True,
        preflight_gap='Original preflight did not exercise support replay after augmenting keep; that changed the helper-derived protected set. Original support stages correctly failed replay and remained baseline. This real-context check covers that missed path.',
        repair_scope='Only reconstruct support using the immutable original parent protection set; identical original proposals, priors, gates and remaining original budgets',
        coordinator_go_still_required=True)
    r.write_new(HERE/'recovery_repair01_preflight.json',output)
    print(json.dumps({k:v for k,v in output.items() if k!='real_context_prechecks'},indent=2))


if __name__ == '__main__': main()
