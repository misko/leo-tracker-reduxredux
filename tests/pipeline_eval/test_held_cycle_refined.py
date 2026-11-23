from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from held_cycle_refined import CFO, FrequencyChanges


def probe(visit=0, radio=0, frequency=10.25):
    return dict(visit_index=visit, receiver_id=radio, candidates=[{CFO: frequency, "candidate_rank": 0}])


def test_capture_scopes_the_actual_receiver_instance():
    def fake(rows):
        return ((0, 42, .1, 12., .4, .2),), "updated"

    policy = SimpleNamespace(amend=fake)
    changes = FrequencyChanges()
    with changes.capture(policy):
        refined, reason = policy.amend(((0, 42, .1, 10.25, .4, .2),))
    assert changes.by_attempt == {0: (10.25, refined[0])}
    assert reason == "updated" and changes.attempted == 1
    assert policy.amend is fake


def test_reconstructs_pre_refinement_view_and_keeps_original_packet():
    changes = FrequencyChanges()
    changes.changed[(0, 0)] = (10.25, 12.)
    old, refined = probe(), probe(frequency=12.)
    other = probe(visit=1)
    restored = changes.original_rows([refined, other])
    assert restored == [old, other]
    assert restored[1] is other
    assert refined["candidates"][0][CFO] == 12


def test_wrong_epoch_lane_or_frequency_is_rejected():
    changes = FrequencyChanges()
    changes.changed[(0, 0)] = (5., 10.25)
    for rows in ([], [probe(radio=1)], [probe(visit=1)], [probe(frequency=9.)], [probe(), probe()]):
        with pytest.raises(ValueError):
            changes.original_rows(rows)
