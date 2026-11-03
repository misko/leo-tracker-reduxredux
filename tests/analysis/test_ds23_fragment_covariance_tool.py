"""Fragment covariance retains variance and never links unrelated RF evidence."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_fragment_covariance import fragment_correlation


def test_only_same_satellite_and_RF_get_correlated_offsets():
    keys=[(1,11e9),(1,11e9),(1,12e9),(2,11e9)]
    r=fragment_correlation(keys,.9)
    assert np.diag(r)==pytest.approx(np.ones(4))
    assert r[0,1]==pytest.approx(.9)
    assert r[0,2]==r[0,3]==0
    assert np.linalg.eigvalsh(r).min()>0


def test_zero_correlation_is_exact_independent_control():
    assert fragment_correlation([(1,1),(1,1)],0)==pytest.approx(np.eye(2))


def test_cholesky_design_preserves_marginal_300Hz_variance():
    r=fragment_correlation([(1,1)]*3,.5);root=np.linalg.cholesky(r)
    design=300*np.eye(3)@root
    assert design@design.T==pytest.approx(300**2*r)


def test_perfect_or_invalid_correlation_is_rejected():
    with pytest.raises(ValueError):fragment_correlation([(1,1)],1.)
