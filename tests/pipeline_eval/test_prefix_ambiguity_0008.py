import pytest

from reports.ALGO08.v3.prefix_ambiguity_0008 import cold_clearance, family_scope


def test_saved_confidence_scope_excludes_the_two_receiver_family():
    curves = {
        "SCAN-RX1-CH1-A": dict(norad=101),
        "SCAN-RX1-CH2-B": dict(norad=101),
        "SCAN-RX1-CH1-C": dict(norad=102),
        "SCAN-RX2-CH2-D": dict(norad=102),
        "SCAN-RX1-CH1-E": dict(norad=103),
    }
    assert family_scope(curves) == {"SCAN-RX1-CH1-A", "SCAN-RX1-CH2-B"}


def test_generic_race_comparison_replays_actual_gap_rule():
    prefix = [dict(score=100., parameters=[0., 0.], drop=.1), dict(score=100.5, parameters=[0., 0.], drop=.1),
              dict(score=102., parameters=[0., 0.], drop=.1)]
    cold = dict(prefix=prefix, routing="ambiguous_gap", gaps=[
        dict(other=2, gap=.5, required=1.), dict(other=3, gap=2., required=1.)])
    assert cold_clearance(cold, 12.5)["minimum_gap_surplus"] == -.5
    with pytest.raises(ValueError, match="does not replay"):
        cold_clearance(dict(cold, routing="winner_raced"), 12.5)
