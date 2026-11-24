import pytest

from reports.ALGO08.v3.balanced_stereo_recovery import preserve_paid, should_recover


@pytest.mark.parametrize(("route", "chosen", "measured", "recover"), (
    ("history", 0, 6, True), ("history", 0, 0, False), ("history", 1, 6, False),
    ("unfiltered", 0, 0, False), ("unfiltered", 6, 6, False),
))
def test_exactly_empty_history_can_use_only_a_nonempty_paid_alternative(route, chosen, measured, recover):
    witness = dict(choice=dict(route=route), selected=chosen, observed=measured)
    assert should_recover(witness) is recover
    if not recover:
        packet = object()
        assert preserve_paid(None, packet, witness) == (packet, witness)


def test_recovery_cannot_admit_hidden_or_unmeasured_factors():
    witness = dict(choice=dict(route="history"), selected=0, observed=1)
    blank = dict(source=dict(probes=[dict(candidates=[])]))
    with pytest.raises(ValueError, match="already measured"):
        preserve_paid(blank, blank, witness)
