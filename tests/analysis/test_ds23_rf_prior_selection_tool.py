"""Selection uses only RF scores, on matched observation identities."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools"))
from probe_ds23_rf_prior_selection import MODELS,choose_by_rf,common_mask


def test_common_mask_does_not_resurrect_any_rejected_observation():
    assert common_mask([1,1,1,0],[[1,0,1,1],[0,1,1,1]]).tolist()==[False,False,True,False]
    with pytest.raises(ValueError):common_mask([1,1],[[1]])


def test_selection_ignores_fitted_c_and_diagnostic_position_error():
    rows={name:dict(c0=dict(score=10),fitted_c=dict(score=-1e6),error_km=0.) for name in MODELS}
    rows['combined']['c0']['score']=9
    rows['combined']['error_km']=999
    assert choose_by_rf(rows)=='combined'
    rows['combined']['c0']['score']=10
    assert choose_by_rf(rows)=='baseline'
