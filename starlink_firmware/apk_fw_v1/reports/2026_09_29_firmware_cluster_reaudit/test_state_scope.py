import pytest
from state_scope import check_baselines, supported_frames


def test_repeated_states_require_training_support_not_future_occurrences():
    summary = dict(qualified_frames=list(range(8)), windows=[
        dict(frame=f, phase_hypothesis=s, label=1)
        for f, s in enumerate([1, 1, 2, 3, 2, 2, 1, 3])])
    train, test, eligible, counts = supported_frames(summary)
    assert train == [0, 1, 2, 3]
    assert test == [6] and eligible == [1] and counts[2] == 1


def test_baseline_check_rejects_inconsistent_reduction():
    metrics = dict(state_over_zero_error_reduction=.6,
                   state_over_global_error_reduction=.2,
                   global_over_zero_error_reduction=.5)
    check_baselines(metrics)
    metrics["state_over_zero_error_reduction"] = .7
    with pytest.raises(AssertionError):
        check_baselines(metrics)
