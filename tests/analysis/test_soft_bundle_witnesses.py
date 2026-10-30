import numpy as np
import pytest
from diagnose_soft_bundle_witnesses import disjoint_witnesses,transfer


def test_excludes_physical_target_overlap_even_when_component_name_differs():
    rows=[dict(component='other-name',observation_ids=['t','w']),dict(component='independent',observation_ids=['a','b'])]
    kept,excluded=disjoint_witnesses(rows,['t'])
    assert kept==rows[1:] and excluded[0]['shared_observation_ids']==['t']
    with pytest.raises(ValueError,match='provenance'):disjoint_witnesses([dict(component='unknown')],['t'])


def test_transfer_requires_two_other_families_and_does_not_fit_target_amplitude():
    t=np.arange(40.);r=100*np.sin(t/6)
    target=dict(component='target',norad=1,receiver=1,channel=1,rf_hz=11.5e9,times_s=t,residual_hz=r)
    witnesses=[dict(target,component='a',norad=2),dict(target,component='b',norad=3)]
    rows=transfer(target,witnesses);primary=next(q for q in rows if q['relation']=='same_receiver' and q['width_s']==6 and q['scaling']=='hz')
    assert primary['supported_points']==40 and primary['corrected_RMS_hz']<primary['baseline_RMS_hz']
    changed=transfer(dict(target,residual_hz=-r),witnesses)
    reverse=next(q for q in changed if q['relation']=='same_receiver' and q['width_s']==6 and q['scaling']=='hz')
    np.testing.assert_array_equal(primary['prediction_hz'],reverse['prediction_hz'])
    assert reverse['corrected_RMS_hz']>reverse['baseline_RMS_hz']
    one=transfer(target,witnesses[:1]);primary=next(q for q in one if q['relation']=='same_receiver' and q['width_s']==6 and q['scaling']=='hz')
    assert primary['supported_points']==0 and primary['corrected_RMS_hz']==primary['baseline_RMS_hz']


def test_witness_training_check_rejects_held_and_guard_points():
    from validate_soft_bundle_witnesses import assert_training_only
    split=dict(block_s=12.,guard_s=2.,held_blocks=[1])
    assert_training_only([dict(times_s=np.array([0.,9.,27.]))],split)
    for time in (10.,12.,23.,26.):
        with pytest.raises(ValueError,match='leaked'):assert_training_only([dict(times_s=np.array([time]))],split)
