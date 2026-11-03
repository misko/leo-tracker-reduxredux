import copy

from probe_ds23_paired_replacement_evidence import decisions


def trial(c0,fitted,valid=True):return dict(paired_valid=valid,arms=dict(c0=dict(corrected_selection_loss=c0),fitted_c=dict(corrected_selection_loss=fitted)))


def test_paired_rule_rejects_actual_0080_sign_pattern_without_changing_trial_or_c0_control():
    s=dict(trials=[trial(99.69571414526217,100.31280558525032)],baseline_corrected_loss=dict(c0=100.,fitted_c=100.),search_penalty=20.)
    result=decisions(s)
    assert result['accepted']['published_c0_positive']
    assert not result['accepted']['paired_positive']
    assert result['best_paired_trial_index']==0


def test_same_c0_best_candidate_used_and_no_geographic_fields_or_new_reranking():
    s=dict(trials=[trial(90,100.1),trial(91,90),trial(1,1,False)],baseline_corrected_loss=dict(c0=100.,fitted_c=100.),search_penalty=20.)
    old=copy.deepcopy(s);result=decisions(s)
    assert result['best_paired_trial_index']==0 and not result['accepted']['paired_positive']
    s['trials'][0]['arms']['c0']['endpoint_latlon']=[0.,0.]
    assert decisions(s)==result and len(old['trials'])==len(s['trials'])


def test_fixed_binary_margin_and_no_candidate_cases():
    s=dict(trials=[trial(98,99)],baseline_corrected_loss=dict(c0=100.,fitted_c=100.),search_penalty=20.)
    r=decisions(s);assert r['accepted']['paired_positive'] and not r['accepted']['paired_2log2_margin']
    s['trials']=[];r=decisions(s)
    assert r['best_paired_trial_index'] is None and not any(r['accepted'].values())
