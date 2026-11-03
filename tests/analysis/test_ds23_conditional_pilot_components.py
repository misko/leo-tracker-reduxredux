from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_conditional_pilot_components import component_geometry,component_segments,conditional_component_prediction


def scene(second_present=True,duplicate=False):
    fs=2500000.;y=np.zeros(25000,complex)
    one=dict(CFO_hz=40000.,offset_samples=.125,modulation_ppm=3.)
    two=dict(CFO_hz=-30000.,offset_samples=-.125,modulation_ppm=-5.)
    epoch1,epoch2=23.2,800.1
    if duplicate:two=one;epoch2=epoch1
    first=component_geometry(y,fs,'lower',epoch1,one)
    second=component_geometry(y,fs,'lower',epoch2,two)
    rng=np.random.default_rng(193);y=.1*(rng.normal(size=len(y))+1j*rng.normal(size=len(y)))
    for ix in component_segments(first,second):
        a=rng.normal(size=8)+1j*rng.normal(size=8)
        b=.7*(rng.normal(size=8)+1j*rng.normal(size=8))
        y[ix]+=first['exact'][ix]@a+.3+.2j
        if second_present:y[ix]+=second['exact'][ix]@b
    return y,fs,epoch1,one,epoch2,two


def test_true_second_component_survives_primary_channel_and_heldout_prediction():
    y,fs,e1,f1,e2,f2=scene()
    result=conditional_component_prediction(y,fs,'lower',e1,f1,e2,f2)
    assert result['two_received_components_supported'],result['checks']
    assert min(f['improvement_over_first'] for f in result['folds'])>.9


def test_nonexistent_secondary_does_not_get_created_by_extra_channel_parameters():
    y,fs,e1,f1,e2,f2=scene(second_present=False)
    result=conditional_component_prediction(y,fs,'lower',e1,f1,e2,f2)
    assert not result['two_received_components_supported']


def test_duplicate_component_cannot_be_claimed_as_an_independent_signal():
    y,fs,e1,f1,e2,f2=scene(duplicate=True)
    result=conditional_component_prediction(y,fs,'lower',e1,f1,e2,f2)
    assert not result['checks']['distinct_design']
    assert not result['two_received_components_supported']
