from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from evaluate_ds23_frequency_selective_pilot import canonical_receiver


def test_zero_based_raw_ids_map_to_canonical_track_owners():
    assert canonical_receiver(0,'DS23-0202-RX1-CH2-T008-RF10959687500.000000')==1
    assert canonical_receiver(1,'DS23-0202-RX2-CH2-T001-RF10959687500.000000')==2


def test_receiver_mismatch_is_not_silently_relabelled():
    with pytest.raises(ValueError):canonical_receiver(1,'DS23-0202-RX1-CH2-T008-RF10959687500.000000')
