import numpy as np
import pytest
from diagnose_pulse_graph_partition import original_winner
from analyze_pulse_graph_measurements import canonical_correction,centered_metrics


def test_original_winner_uses_margin_and_original_tie_break_not_cfo_proximity():
    candidates=[dict(candidate_rank=k,fractional_margin=m,passed_fractional_margin_gate=g,fractional_tracking_cfo_hz=f)
        for k,m,g,f in [(0,.2,True,100.),(1,.2,True,200.),(2,.9,False,300.)]]
    assert original_winner(candidates,100.)['candidate_rank']==0
    with pytest.raises(ValueError,match='mismatch'):original_winner(candidates,200.)
    with pytest.raises(ValueError,match='no eligible'):original_winner([candidates[2]],300.)


def test_canonical_correction_preserves_dc_and_boundary_and_bin_translation():
    response=dict(step_hz=500.,reported_offset_hz=[-250.,-100.,0.,100.,250.],actual_offset_hz=[-250.,-125.,0.,125.,250.])
    delta,eligible=canonical_correction([0.,500.,399000.,-399000.,1100.,1600.,-1100.],response)
    np.testing.assert_array_equal(eligible,[False,False,False,False,True,True,True])
    np.testing.assert_allclose(delta,[0,0,0,0,25,25,-25])
    with pytest.raises(ValueError,match='finite'):canonical_correction([np.nan],response)


def test_centered_metrics_does_not_remove_a_slope_or_step():
    t=np.arange(10.)+178;r=1000+3*(t-178)
    result=centered_metrics(t,r)
    assert result['slope_hz_s']==pytest.approx(3.)
    assert result['late_minus_early_hz']==pytest.approx(15.)
    assert result['centered_RMS_hz']>8
