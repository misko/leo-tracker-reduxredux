"""Synthetic alias conventions preserve the entire ideal frequency curve."""
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from probe_ds23_synthetic_closure import alias_encode
from leo.analysis.research.retained_track_likelihood import PERIOD,profile,whitening


@pytest.mark.parametrize('cycles',[-9,-1,0,1,12])
def test_alias_round_trip_and_original_profile_agree(cycles):
    f=cycles*PERIOD+np.linspace(-50000,50000,60)
    values,alias=alias_encode(f)
    np.testing.assert_allclose(values+alias*PERIOD,f,atol=1e-9,rtol=0)
    result=profile(values,f,*whitening(np.arange(60.)))
    assert alias==cycles==int(result['alias'][0])
    assert result['rms'][0]<1e-8


def test_generator_rejects_unknown_or_nonfinite_frequency():
    for f in [[],[float('nan')],[[1,2]]]:
        with pytest.raises(ValueError):alias_encode(f)
