from collections import Counter
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'reports/ALGO08/v3'))

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from rescue_phase_prepare import PreparedFinePhase,ShadowMismatch,measured_fine


def bank():
    generator = np.random.default_rng(12)
    epochs = np.array([-20.,-0.5,1.5,17.,40.])
    return dict(time_s=epochs,position_km=generator.normal(size=(3,len(epochs),3))+[7000.,-1200.,3440.],
                velocity_km_s=generator.normal(size=(3,len(epochs),3))+[6.,2.,-3.])


def test_fine_projection_keeps_exact_bits_for_every_satellite_phase_and_duplicate_epoch():
    data = bank()
    times,phases = np.array([-5.,-.5,1.5,1.5,10.,30.]),np.linspace(-10.,10.,81)
    place = 37.8,-122.48
    prepared = PreparedFinePhase(data,times,phases)
    for label in range(len(data['position_km'])):
        repeated = dict(data,time_s=data['time_s'],**{
            key:np.repeat(data[key][[label]],len(phases),axis=0) for key in ('position_km','velocity_km_s')
        })
        old = paired_phase_frequency(repeated,np.tile(times,len(phases)),np.repeat(np.arange(len(phases)),len(times)),phases,*place)
        for original,candidate in zip(old,prepared.project(label,place),strict=True):
            assert candidate.shape == (len(phases),len(times))
            np.testing.assert_array_equal(original.view(np.uint64),candidate.ravel().view(np.uint64))
    assert prepared.replicated_bytes == 81*5*3*8*2


def test_invalid_knots_or_phase_outside_original_domain_are_ineligible():
    data = bank()
    with pytest.raises(ValueError,match='extrapolates'):
        PreparedFinePhase(data,np.array([20.]),np.array([25.]))
    data['time_s'][3] = data['time_s'][2]
    with pytest.raises(ValueError,match='Unsupported'):
        PreparedFinePhase(data,np.array([20.]),np.array([1.]))


def test_local_shadow_alternates_whole_calls_and_never_adopts_a_difference():
    trace,audit = [],[]

    def operation(name, value):
        def run(_stock,counts,*_rest):
            trace.append(name)
            counts['priced'] += 1
            return ([{'cost':value}],1)
        return run

    bound = measured_fine(operation('a',1.),operation('b',1.),audit)
    counts = Counter()
    args = (None,counts,None,None,{'key':'track'},None,None,None,None,None)
    assert bound(*args) == ([{'cost':1.}],1)
    assert bound(*args) == ([{'cost':1.}],1)
    assert trace == ['a','b','b','a']
    assert counts == {'priced':2}
    assert [x['alternatives'] for x in audit] == [1,1]
    with pytest.raises(ShadowMismatch,match='alternatives changed'):
        measured_fine(operation('a',1.),operation('b',2.),[])(*args)
