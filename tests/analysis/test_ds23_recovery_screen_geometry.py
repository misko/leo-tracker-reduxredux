"""Equivalent Doppler/elevation and aliases, without changing fitted geometry."""
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_recovery_screen_geometry import prepare_screen_geometry,screen_frequency,install_for_screening
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry,phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import profile,whitening


def bank():
    t=np.linspace(-30,330,361);rng=np.random.default_rng(701)
    p=rng.normal(size=(7,1,3))*1000+np.array([7000.,-2000.,3000.])
    v=rng.normal(size=(7,1,3))*3
    return dict(time_s=t,position_km=p+t[None,:,None]*v,velocity_km_s=np.broadcast_to(v,(7,len(t),3)).copy())


@pytest.mark.parametrize('phase',[-15.,0.,15.])
def test_frequency_and_elevation_equal_original(phase):
    b=bank();times=np.linspace(0,300,51);phases=np.linspace(phase/2,phase,7)
    old=prepare_phase_geometry(b,times,phases);new=prepare_screen_geometry(b,times,phases)
    for location in [(37.906,-122.545),(-25.,130.)]:
        f,e,_=phase_linear_frequency(old,*location);ff,ee,unused=screen_frequency(new,*location)
        np.testing.assert_array_equal(ff,f);np.testing.assert_array_equal(ee,e)
        y=f[0]+123456.
        a=profile(y,f,*whitening(times));c=profile(y,ff,*whitening(times))
        for key in a:np.testing.assert_array_equal(a[key],c[key])
        assert unused is None


def test_phase_bounds_and_immutable_arrays_are_preserved():
    b=bank()
    with pytest.raises(ValueError,match='extrapolates'):prepare_screen_geometry(b,np.array([325.]),15.)
    result=prepare_screen_geometry(b,np.array([0.,1.]))
    assert not result.geometry.position_km.flags.writeable


def test_installation_does_not_modify_original_geometry_module():
    fake=SimpleNamespace(prepare_phase_geometry=prepare_phase_geometry,phase_linear_frequency=phase_linear_frequency)
    install_for_screening(fake)
    assert fake.prepare_phase_geometry is prepare_screen_geometry
    import leo.analysis.research.phase_linear_geometry as original
    assert original.prepare_phase_geometry is prepare_phase_geometry
