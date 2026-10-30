import pytest
from report_cross_family_prediction import held_metrics


def row(key,ids,residual):
    return dict(component=key,observation_ids=ids,residual_hz=residual)


def test_held_rms_is_point_weighted_and_requires_identical_observations():
    a=[row('a',['1'],[0.]),row('b',['2','3','4'],[4.,4.,4.])]
    b=[row('a',['1'],[0.]),row('b',['2','3','4'],[2.,2.,2.])]
    result=held_metrics(a,b,lambda _:True)
    assert result['points']==4
    assert result['control_RMS_hz']==pytest.approx(12**.5)
    assert result['RMS_gain_hz']==pytest.approx(3**.5)
    with pytest.raises(ValueError,match='sets differ'):
        held_metrics(a,[b[0],row('b',['2','3','5'],[2.,2.,2.])],lambda _:True)


def test_duplicate_and_empty_held_groups_are_explicit():
    a=[row('a',['1'],[2.]),row('b',['1'],[3.])]
    with pytest.raises(ValueError,match='twice'):held_metrics(a,a,lambda _:True)
    assert held_metrics(a,a,lambda _:False)['RMS_gain_hz'] is None
