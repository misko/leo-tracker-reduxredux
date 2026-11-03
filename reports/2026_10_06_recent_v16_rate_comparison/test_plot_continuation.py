import pytest
from plot_continuation import records


def case():
    return dict(scan='example',refinement='refined',model='V16',cone='off',arm='zero-c',
        original=dict(converged=False,objective=100.,distance_m=100.),
        objective=90.,distance_m=200.,converged=True)


def test_plot_preserves_worsening_position_despite_better_objective():
    r=case();out=records([r])[0]
    assert out['gain']==10 and out['after']>out['before']
    r['original']['converged']=True
    assert records([r])==[]


def test_plot_rejects_duplicates_and_increased_loss():
    r=case()
    with pytest.raises(ValueError,match='Duplicate'):records([r,r])
    r['objective']=101
    with pytest.raises(ValueError,match='increased'):records([r])
