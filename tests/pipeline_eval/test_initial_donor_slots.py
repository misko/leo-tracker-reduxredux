from importlib import import_module
from pathlib import Path

import pytest

from tools.pipeline_eval.variants.experimental.residual_schedule import Replay
from tools.pipeline_eval.variants.experimental.initial_donors import InitialDonors


def test_initial_slots_inform_votes_without_extending_activity():
    control = Replay("conditional")
    initialized = InitialDonors()
    schedules = [[], []]
    retained = [[], []]
    for i in range(21):
        row = dict(receiver_id=1, channel=4, actual_rf_hz=12e9,
                   valid_start_counter=i*5_000_000)
        primary = dict(candidate_rank=0, fractional_tracking_cfo_hz=1000.,
                       fractional_margin=1.)
        residual = dict(primary, candidate_rank=1, fractional_tracking_cfo_hz=-17_000.)
        first = dict(primary, fractional_tracking_cfo_hz=-17_000.) if i in (0, 3, 4) else primary
        for j, policy in enumerate((control, initialized)):
            full, _, selected = policy.visit(row, lambda take: [first, residual] if take and i == 1 else [first])
            schedules[j].append(full)
            retained[j].append(selected)
        assert control.last_residual == initialized.last_residual
        if i >= 14:
            assert dict(control.continuation.by_lane) == dict(initialized.continuation.by_lane)
    assert [i for i in range(21) if schedules[0][i] != schedules[1][i]] == [1, 2]
    assert retained[0][4] == [] and retained[1][4] == [dict(primary, fractional_tracking_cfo_hz=-17_000.)]
    assert control.opportunities == initialized.opportunities


def test_prefix_cannot_reuse_a_suffix_until_every_lane_converges(monkeypatch):
    path = Path(__file__).resolve().parents[2]/"reports/ALGO08/single-core-2x"
    monkeypatch.syspath_prepend(str(path))
    trial = import_module("initial_donor_trial")
    rows = [dict(receiver_id=i % 2, visit_index=i, channel=2, actual_rf_hz=8e9, valid_start_counter=i*5000)
            for i in range(30)]
    runner = trial.Comparison()
    with pytest.raises(ValueError, match="fifteen visits"):
        trial.prefix_limit(rows[:-1])
    assert trial.prefix_limit(rows) == 30
    for row in rows[:-1]:
        runner.visit(row, lambda full: [])
    with pytest.raises(ValueError, match="converge"):
        runner.check_join()
    runner.visit(rows[-1], lambda full: [])
    runner.check_join()
    with pytest.raises(ValueError, match="published row"):
        runner.visit(dict(rows[-1], valid_start_counter=200000), lambda full: [], {})
