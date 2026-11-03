"""Residual matching cannot duplicate measurements or fabricate interpolation."""

import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from audit_ds23_learned_residuals import nearest_pairs


def test_nearest_distance_has_priority_and_neither_side_is_reused():
    a,b=nearest_pairs([0,.1,.2],[.11,.21],.5)
    assert len(a)==len(set(a))==len(b)==len(set(b))==2
    assert set(zip(a,b))=={(1,0),(2,1)}


def test_distant_samples_and_empty_inputs_make_no_pairs():
    assert len(nearest_pairs([0],[1],.5)[0])==0
    assert len(nearest_pairs([],[])[0])==0


def test_nonfinite_times_are_rejected():
    with pytest.raises(ValueError):nearest_pairs([np.nan],[0])
