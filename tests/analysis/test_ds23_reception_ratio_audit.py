from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from audit_ds23_reception_ratio import held_family_loss,permuted_features


def evidence():
    return [dict(norad=f,band=b,feature=f/5.,log_ratio=b+2*f/5.,median_time_s=150.)
            for f in range(6) for b in [0,1]]


def test_direction_predicts_held_families_when_time_is_constant():
    rows=evidence()
    assert held_family_loss(rows,True,True)['squared_error']<.001
    assert held_family_loss(rows,time=True)['squared_error']>1


def test_family_permutation_keeps_both_bands_together():
    rows=evidence();shuffled,_=permuted_features(rows,np.random.default_rng(2))
    for f in range(6):
        assert len({r['feature'] for r in shuffled if r['norad']==f})==1
    assert sorted(r['feature'] for r in shuffled)==sorted(r['feature'] for r in rows)
    assert all(a['log_ratio']==b['log_ratio'] for a,b in zip(rows,shuffled,strict=True))
