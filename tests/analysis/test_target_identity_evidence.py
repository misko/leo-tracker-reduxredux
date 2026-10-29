import copy
import pytest
from leo.analysis.research.target_identity_evidence import evidence_ablation


def example():
    folds=[]
    for seed in range(3):
        proposals=[]
        for norad,training,held in [(1,100.,20.),(2,150.,21.)]:
            scores=dict(negative_twice_log_density=held,training_negative_twice_log_density=training,rms_hz=10.)
            row=dict(scores={'target':scores,'conditional_target':scores},final_phase_change_s=0.,minimum_target_elevation_deg=20.)
            proposals.append(dict(norad=norad,alias=0,arms={'c0':copy.deepcopy(row),'fitted_c':copy.deepcopy(row)}))
        folds.append(dict(seed=seed,proposals=proposals))
    return dict(folds=folds,identity_score_name='conditional_target')


def test_evidence_ablation_preserves_inputs_and_independent_held_adequacy():
    source=example();before=copy.deepcopy(source);r=evidence_ablation(source)
    assert source==before
    assert r['original_annotation']['status']=='ambiguous_identity'
    assert r['annotation']['status']=='conditionally_supported_identity'
    assert r['annotation']['norad']==1
    assert r['annotation']['minimum_margin']==51
    assert r['training_evidence_annotation']['minimum_margin']==50
    assert r['no_accepted_associations']
    source['folds'][0]['proposals'][0]['arms']['c0']['scores']['target']['rms_hz']=500.
    assert evidence_ablation(source)['annotation']['status']=='prediction_mismatch'


def test_cut_scores_cannot_be_misreported_as_exact_joint_evidence():
    source=example();source['folds'][0]['proposals'][0]['arms']['c0']['scores']['conditional_target']['receiver_posterior_frozen']=True
    with pytest.raises(ValueError,match='ordinary mixture'):evidence_ablation(source)
