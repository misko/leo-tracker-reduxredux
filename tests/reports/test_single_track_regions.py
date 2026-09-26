"""Synthetic checks of physical offset sign and pilot phase gauge."""
import importlib.util
from pathlib import Path
import sys
import numpy as np

DIRECTORY=Path(__file__).resolve().parents[2]/'reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track'
sys.path.insert(0,str(DIRECTORY))
spec=importlib.util.spec_from_file_location('track_regions',DIRECTORY/'compare_pilot_regions.py')
M=importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

def test_positive_receiver_offset_excludes_upper_wrapped_band():
    f=np.array([-4.95e6,0,4.2e6,4.4e6])
    masks,bounds=M.masks(f,682434.861,125593.562)
    np.testing.assert_array_equal(masks['broadband'],[True,True,True,False])
    assert np.isclose(bounds[1]-bounds[0],1875000)
    assert not np.any(masks['pilot_band']&masks['outside_pilot'])

def test_frequency_correction_sign_preserves_injected_phase():
    n=np.arange(16384);t=n/M.RATE
    left=np.exp(2j*np.pi*1e6*t)
    right=left*np.exp(1j*(.7+2*np.pi*682434.861*t))
    phase,coherence=M.cross(left,right*np.exp(-2j*np.pi*682434.861*t))
    assert abs(phase-np.degrees(.7))<1e-8
    assert abs(coherence-1)<1e-12

def test_known_pilot_projection_preserves_receiver_phase():
    from leo.analysis.starlink.templates import qin_edge_pilot_frame
    from leo.contracts.states import StarlinkEdge
    raw=qin_edge_pilot_frame(M.RATE,'upper').astype(complex)
    n=np.arange(len(raw));phase=-.8;cfo=125593.562
    left=raw*np.exp(2j*np.pi*cfo*n/M.RATE)
    right=left*np.exp(1j*phase)
    pilots=[M._KnownPilotDemodulator(x,M.RATE,StarlinkEdge.UPPER,cfo).frame(0) for x in [left,right]]
    exact=M.qin_edge_pilot_symbols('upper')
    channels=[np.mean(p*np.conj(exact),axis=0) for p in pilots]
    measured,coherence=M.cross(*channels)
    assert abs(measured-np.degrees(phase))<1e-8
    assert abs(coherence-1)<1e-12
