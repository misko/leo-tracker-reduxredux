from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_reception_anchor_pairs import counterpart
from ds23_frame_registration import PERIOD


def test_unique_opposite_RX_peak_matches_across_CFO_and_epoch_aliases():
    a=dict(epoch=100.,cfo=110000.)
    b=dict(epoch=100.+2.5e6/750+.1,cfo=110000.+50000.-PERIOD)
    assert counterpart(a,[b],50000.,2.5e6)==b


def test_epoch_and_frequency_must_both_match_and_ambiguity_is_not_ranked_away():
    a=dict(epoch=100.,cfo=10000.)
    wrong_frequency=dict(epoch=100.,cfo=20000.)
    wrong_epoch=dict(epoch=101.,cfo=10000.)
    assert counterpart(a,[wrong_frequency,wrong_epoch],0.,2.5e6) is None
    assert counterpart(a,[dict(a),dict(a)],0.,2.5e6) is None


def test_invalid_matching_rate_is_explicit():
    with pytest.raises(ValueError):counterpart(dict(epoch=0,cfo=0),[],0,0)
