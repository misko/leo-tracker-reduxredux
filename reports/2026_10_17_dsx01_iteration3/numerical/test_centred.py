import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from centred import CentredObjective

spec=importlib.util.spec_from_file_location('centred_fixture',Path(__file__).resolve().parents[2]/
    '2026_10_16_dsx01_iteration2/test_bank_expansion.py')
fixture=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=fixture
spec.loader.exec_module(fixture)
case=fixture.case


def test_original_objective_difference_and_gradients_preserved(case):
    ctx,_=case
    centred=CentredObjective(ctx.model,ctx.vector,ctx.nuisance)
    zero=centred.evaluate_joint(ctx.vector,ctx.nuisance)
    assert zero[0]==0.
    vector=ctx.vector.copy();vector[2]+=.001
    a=ctx.model.evaluate_joint(vector,ctx.nuisance)
    b=centred.evaluate_joint(vector,ctx.nuisance)
    assert b[0]==pytest.approx(a[0]-centred.reference_objective,abs=1e-10)
    for aa,bb in zip(a[1:3],b[1:3]):np.testing.assert_array_equal(aa,bb)
    assert centred.calls==3
    assert centred.score is ctx.model.score and centred.bank is ctx.bank


def test_sub_ulp_total_descent_is_resolved_without_changing_gradient():
    class Model:
        def evaluate_details(self,v,n):
            rows=np.full(5000,10.)
            rows[0]+=float(v[0])*1e-12
            return (float(rows.sum()),np.array([1e-12]),np.zeros(0),None),dict(row_nll=rows,prior_penalty=0.)
    model=Model();old=np.array([0.]);new=np.array([.01])
    assert model.evaluate_details(old,[])[0][0]==model.evaluate_details(new,[])[0][0]
    centred=CentredObjective(model,old,[])
    assert centred.evaluate_joint(new,[])[0]>0
    np.testing.assert_array_equal(centred.evaluate_joint(new,[])[1],[1e-12])


def test_changed_row_inventory_rejected():
    class Model:
        def evaluate_details(self,v,n):
            return (0.,[],[],None),dict(row_nll=np.zeros(int(v[0])),prior_penalty=0.)
    centred=CentredObjective(Model(),[2],[])
    with pytest.raises(ValueError,match='same scored rows'):
        centred.evaluate_joint([3],[])
