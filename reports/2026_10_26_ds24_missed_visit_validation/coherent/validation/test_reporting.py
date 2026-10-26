from pathlib import Path
import json
import math
HERE=Path(__file__).resolve().parent
def read(name):return json.loads((HERE/name).read_text())


def test_native_owner_graph_and_satellite_denominators():
    summary=read('summary.json');evaluation=read('position_evaluation_native.json')
    assert sum(c['native_added'] for c in summary['cases'])==summary['new_native']
    assert sum(c['new_in_graph'] for c in summary['cases'])==summary['new_in_graph']
    assert sum(c['new_curved'] for c in summary['cases'])==summary['new_curved']
    for row in evaluation['rows']:
        for arm in row['arms'].values():
            assert arm['total_GLRT_count']==arm['original_GLRT_count']+arm['native_added_count']
            assert math.isclose(arm['associated_GLRT_fraction'],arm['accepted_GLRT_count']/arm['total_GLRT_count'])
            assert set(arm['added_curved_ids']).isdisjoint(arm['added_predictive_ids'])
            assert set(arm['added_curved_ids']+arm['added_predictive_ids'])<=set(arm['added_accepted_ids'])


def test_failed_attempts_preserved_and_continuations_do_not_reset_budget():
    first=read('position_terminal_seal.json');final=read('position_final_terminal_seal.json')
    assert first['all_terminal'] and all(r['status']=='failed' for r in first['results'])
    assert final['all_terminal'] and final['inputs_and_first_attempt_artifacts_unchanged']
    assert not final['denied_reads']
    for result in final['results']:
        assert result['status']=='complete' and result['uid']==1000 and result['fresh_ALGO02_reruns']==0
        assert result['total_numerical_seconds']<=240
        assert math.isclose(result['first_attempt_seconds']+result['continuation_seconds'],result['total_numerical_seconds'])


def test_c_arm_ids_and_alias_normalization_preserve_scientific_metrics():
    original=read('position_evaluation.json');native=read('position_evaluation_native.json')
    assert native['rows']==original['rows'] and native['effects']==original['effects']
    for row in native['rows']:
        for key in ('added_curved_ids','added_predictive_ids'):
            assert row['arms']['c0'][key]==row['arms']['fitted_c'][key]
    for attribution in native['attribution']:
        for identity in attribution['new_likelihood_identities']:
            assert identity['membership']['alias_coordinate'].startswith('total native CFO')
            assert isinstance(identity['membership']['alias_lift'],int)
