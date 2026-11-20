import pytest

from tools.pipeline_eval.qualification.adaptive_arrival import join_events, validate_event
from tools.pipeline_eval.variants.arrival_policy import ArrivalPolicy


@pytest.mark.parametrize(
    ("mode", "first", "under_load"),
    [("adaptive", "fifth", "stock"), ("stock", "stock", "stock"), ("fifth", "fifth", "fifth")],
)
def test_policy_uses_the_number_of_unfinished_visits(mode, first, under_load):
    receiver = ArrivalPolicy(mode)
    assert receiver.admit() == (0, first)
    assert receiver.admit() == (1, under_load)
    assert receiver.admit() == (2, None)
    receiver.finish()
    assert receiver.admit() == (1, under_load)
    receiver.finish()
    receiver.finish()
    assert receiver.admit() == (0, first)
    receiver.finish()
    with pytest.raises(ValueError, match="no admitted"):
        receiver.finish()


def input_event():
    return dict(
        visit=0,
        arrival_ns=14,
        delivery_clock={"monotonic_ns": 14},
        sample_start=203,
        sample_end=403,
        status="processed",
        full_visit_sha256="a" * 64,
    )


def test_both_native_controls_must_identify_the_same_waveform():
    first = input_event()
    second = dict(first, full_visit_sha256="b" * 64)
    event = join_events([first], [second])[0]
    assert (event["stock"], event["fifth"]) == ("a" * 64, "b" * 64)
    with pytest.raises(ValueError, match="physical opportunity"):
        join_events([first], [dict(second, sample_start=202)])
    with pytest.raises(ValueError, match="hardware exclusion"):
        join_events(
            [dict(first, status="invalid_capture")], [dict(second, status="invalid_capture")]
        )


def test_retained_hash_must_agree_with_the_actual_admission_branch():
    first = input_event()
    expected = join_events([first], [dict(first, full_visit_sha256="b" * 64)])[0]
    event = dict(
        expected,
        outcome="emitted",
        policy="stock",
        actual_sha256=expected["stock"],
        released_ns=20,
        started_ns=25,
        emitted_ns=66,
        outstanding_at_admission=1,
    )
    validate_event(event, expected, "adaptive")
    with pytest.raises(ValueError, match="selected detector"):
        validate_event(dict(event, actual_sha256=expected["fifth"]), expected, "adaptive")
    with pytest.raises(ValueError, match="causal admission"):
        validate_event(dict(event, outstanding_at_admission=0), expected, "adaptive")
    dropped = dict(event, outcome="queue_drop", policy=None, outstanding_at_admission=2)
    dropped.pop("actual_sha256")
    validate_event(dropped, expected, "adaptive")
    with pytest.raises(ValueError, match="available slot"):
        validate_event(dict(dropped, outstanding_at_admission=1), expected, "adaptive")
