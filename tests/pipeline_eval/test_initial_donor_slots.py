from tools.pipeline_eval.variants.experimental.residual_schedule import Replay


def test_initial_slots_inform_votes_without_extending_activity():
    control = Replay("conditional")
    initialized = Replay("conditional", initialize_donors=True)
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
    assert retained[0][4] == [] and retained[1][4] == [first | {"fractional_tracking_cfo_hz": -17_000.}]
    assert control.opportunities == initialized.opportunities
