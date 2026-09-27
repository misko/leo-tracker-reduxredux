from dataclasses import replace
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from diagnostic import compatible
from test_early_confirmed import fixtures


def test_pair_transport_handles_middle_and_reverse_late_windows():
    rate=2500000
    first=fixtures.Observation(0,10,250000,317.)
    second=replace(first,probe_index=8,probe_start_sample=200000)
    assert compatible(first,second,rate)
    assert not compatible(first,replace(second,tracking_cfo_hz=second.tracking_cfo_hz+8001),rate)
    assert not compatible(first,replace(second,local_epoch_sample=327.),rate)
    assert not compatible(first,replace(second,probe_index=9),rate)
    assert not compatible(first,None,rate)
