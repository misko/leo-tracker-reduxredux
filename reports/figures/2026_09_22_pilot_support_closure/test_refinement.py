import numpy as np
import pytest
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import ReceiverPhaseSeed, shared_frame_starts, extract_dual_receiver_phase_with_offset_authority_shared_residual
from leo.analysis.starlink.templates import qin_edge_pilot_frame
from refined_pilot import refine_shared_pilot

@pytest.mark.parametrize('edge',['lower','upper'])
@pytest.mark.parametrize('authority_error_hz',[-140.,100.])
def test_recorrelation_transports_phase_to_frame_reference(edge,authority_error_hz):
    rate=2500000.;epoch=40000;n=100000;delta=-619159.5;frequency0=-82137.25;phase=.73
    template=np.asarray(qin_edge_pilot_frame(rate,edge),complex);iq=np.zeros((n,2),complex)
    starts=shared_frame_starts(n,rate,epoch);rng=np.random.default_rng(811)
    for start in starts:
        indexes=start+np.arange(len(template));common=rng.uniform(-np.pi,np.pi)
        iq[indexes,0]=template*np.exp(1j*(common+2*np.pi*frequency0*indexes/rate))
        iq[indexes,1]=template*np.exp(1j*(common+phase+2*np.pi*(frequency0+delta)*indexes/rate))
    seeds=(ReceiverPhaseSeed(-82000.,0.),ReceiverPhaseSeed(-82000.+delta+authority_error_hz,0.))
    first,second=refine_shared_pilot(iq,rate,edge,epoch,seeds,delta+authority_error_hz,frame_radius=9)
    def error(o):return abs(np.degrees(np.angle(np.exp(1j*(o.wrapped_phase_rad-phase-2*np.pi*delta*o.center_sample/rate)))))
    assert error(first)>3
    assert error(second)<.05
    assert abs(second.relative_frequency_hz-delta)<.1
