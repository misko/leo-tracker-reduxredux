from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_reception_ratio import beam_contrast,logit_ratio,cross_validate


def test_nominal_mount_contrast_is_symmetric_and_prefers_west_on_first_RX():
    assert beam_contrast(270.,70.)>0
    assert beam_contrast(90.,70.)<0
    assert beam_contrast(270.,70.)==pytest.approx(-beam_contrast(90.,70.))
    assert beam_contrast(0.,90.)==pytest.approx(0.,abs=1e-15)


def test_reception_ratio_reverses_when_receivers_are_swapped():
    np.testing.assert_allclose(logit_ratio([.1,.3],[.4,.6]),-logit_ratio([.4,.6],[.1,.3]))


def test_held_family_prediction_excludes_every_row_of_that_family():
    rows=[dict(norad=k,band=b,feature=(k-4)*.1,log_ratio=b*.3+2*(k-4)*.1) for k in range(9) for b in [0,1]]
    result=cross_validate(rows)
    assert result['qualified']
    for fold in result['folds']:assert fold['norad'] not in fold['training_families']


def test_one_family_cannot_calibrate_the_beam_by_duplicating_points():
    rows=[dict(norad=1,band=0,feature=k*.1,log_ratio=k*.2) for k in range(100)]
    assert not cross_validate(rows)['qualified']
