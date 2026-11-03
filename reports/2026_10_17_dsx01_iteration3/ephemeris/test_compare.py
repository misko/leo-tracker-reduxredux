"""Contract-level ephemeris replacement checks; no archive or hardware needed."""
import importlib.util
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from compare import with_bank, epoch_summary
from leo.contracts.regional_position import PositionOrbitBank

spec=importlib.util.spec_from_file_location('expansion_fixture',Path(__file__).resolve().parents[2]/
                                         '2026_10_16_dsx01_iteration2/test_bank_expansion.py')
fixtures=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=fixtures
spec.loader.exec_module(fixtures)
case=fixtures.case


def test_identical_ephemerides_preserve_complete_objective_and_gradient(case):
    context,_=case
    copy=with_bank(context,context.bank)
    assert copy.model is not context.model
    for a,b in zip(context.model.evaluate_joint(context.vector,context.nuisance)[:3],
                   copy.model.evaluate_joint(copy.vector,copy.nuisance)[:3]):
        np.testing.assert_array_equal(a,b)
    copy.vector[0]+=1
    assert copy.vector[0]!=context.vector[0]


def test_changed_ephemerides_change_frequency_but_not_calibration(case):
    context,_=case
    bank=context.bank
    velocity=bank.velocity_km_s.copy()
    velocity[:,:,2]+=.01
    new=PositionOrbitBank(bank.numbers,bank.nodes_s,bank.position_km,velocity)
    copy=with_bank(context,new)
    a=context.model.evaluate_joint(context.vector,context.nuisance)[3].residual_hz
    b=copy.model.evaluate_joint(copy.vector,copy.nuisance)[3].residual_hz
    assert not np.allclose(a,b)
    np.testing.assert_array_equal(copy.model.original.baseline,context.model.original.baseline)


def test_changed_candidate_order_rejected(case):
    context,_=case
    with pytest.raises(ValueError,match='ordered'):
        with_bank(context,context.bank.select([2,1,0]))


def test_held_measurements_do_not_change_replaced_training_objective(case):
    context,_=case
    obs=replace(context.observations,measured_hz=context.observations.measured_hz+
                np.where(context.train_mask,0.,987654.))
    a=with_bank(context,context.bank)
    b=with_bank(replace(context,observations=obs),context.bank)
    for aa,bb in zip(a.model.evaluate_joint(a.vector,a.nuisance)[:3],
                     b.model.evaluate_joint(b.vector,b.nuisance)[:3]):
        np.testing.assert_array_equal(aa,bb)


def test_element_age_is_matched_by_identity_not_catalogue_order():
    class Catalogue:
        satellite_numbers=(20,10,30)
        def element_epoch_utc_ns(self):
            return (int(7.2e12),0,int(3.6e12))
    result=epoch_summary(Catalogue(),[10,20],int(3.6e12))
    assert result['signed_age_h']==[1.,-1.]
    assert result['negative_signed_age_count']==1
    assert result['median_absolute_age_h']==1.
    with pytest.raises(ValueError,match='absent'):
        epoch_summary(Catalogue(),[99],0)
