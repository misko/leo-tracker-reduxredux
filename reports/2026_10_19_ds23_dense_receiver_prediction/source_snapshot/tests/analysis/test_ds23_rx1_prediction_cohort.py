from probe_ds23_rx1_prediction_cohort import qualify


def row(rx, loss):
    return dict(receiver=rx, prediction=dict(negative_twice_log_density=loss))


def test_policy_needs_predictions_both_receivers_RF_gain_and_paired_gates():
    base = [row(1, 20), row(2, 20)]
    improved = [row(1, 15), row(2, 19)]
    assert qualify(base, improved, True, -10)['qualified']
    assert not qualify(base, [row(1, 10), row(2, 21)], True, -10)['qualified']
    assert not qualify(base, improved, False, -10)['qualified']
    assert not qualify(base, improved, True, 1)['qualified']
    assert not qualify(base, [row(1, 19.8), row(2, 19.8)], True, -10)['qualified']
    assert not qualify([], [], True, -10)['qualified']
