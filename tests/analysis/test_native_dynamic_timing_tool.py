import numpy as np
from probe_native_dynamic_timing import quantize,scene,FS


def test_quantized_injection_preserves_complex_direction_without_clipping():
    values=np.array([1+2j,2-1j,-1-2j,-2+1j])
    samples=quantize(values)
    assert samples.dtype==np.dtype('<i2') and samples.shape==(4,1,2)
    restored=samples[:,0,0]+1j*samples[:,0,1]
    np.testing.assert_allclose(restored/restored[0],values/values[0],atol=1e-4)
    assert np.max(abs(samples))<32767


def test_geometric_doppler_and_arrival_delay_have_consistent_direction():
    _,before,delay_before,cfo_before=scene('lower',-60)
    _,after,delay_after,cfo_after=scene('lower',60)
    assert before.shape==after.shape==(FS//50,1,2)
    assert cfo_before>100000>cfo_after
    assert delay_after>delay_before  # centered probes occur just after either scene time
