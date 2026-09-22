"""Report-local pilot estimator with a shared branch and refined phase epoch."""
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import extract_dual_receiver_phase_with_offset_authority_shared_residual

def refine_shared_pilot(iq,rate,edge,epoch,seeds,authority,*,frame_radius=16):
    """Return initial and re-correlated observations on one frequency branch.

    The initial broadband authority chooses the branch. Frame phase estimates
    its local residual, then both RXs are re-correlated using that refined
    difference. This removes the differential within-symbol phase rotation
    that otherwise biases the reported frame-start phase. No broadband phase
    values or held comparison offsets are inputs.
    """
    fn=extract_dual_receiver_phase_with_offset_authority_shared_residual
    first=fn(iq,rate,edge,epoch,seeds,authority,common_reference_sample=0,frame_radius=frame_radius).observation
    if abs(first.relative_frequency_hz-authority)>=375:
        raise ValueError('Pilot refinement leaves the independently selected frame-frequency branch')
    refined=fn(iq,rate,edge,epoch,seeds,first.relative_frequency_hz,common_reference_sample=0,frame_radius=frame_radius).observation
    return first,refined
