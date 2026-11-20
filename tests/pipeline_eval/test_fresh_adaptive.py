import pytest

from tools.pipeline_eval.qualification.adaptive_arrival import join_events, validate_event
from tools.pipeline_eval.qualification.fresh_adaptive import CPUS, EXPECTED, ORDER


def events(status="processed"):
    base = dict(
        visit=0,
        arrival_ns=100,
        delivery_clock={"monotonic_ns": 100},
        sample_start=301,
        sample_end=501,
        status=status,
    )
    stock = dict(base, full_visit_sha256="a" * 64)
    fifth = dict(base, full_visit_sha256="b" * 64)
    return stock, fifth


def test_new_cases_keep_balanced_order_and_distinct_fixed_manifest():
    assert tuple(CPUS.values()) == (18, 19)
    first, second = ORDER.values()
    assert first == second[::-1]
    assert [n for n, _ in EXPECTED.values()] == [6770, 6769]


def test_actual_emission_must_match_adaptive_slot_policy_and_exact_envelope():
    stock, fifth = events()
    (scheduled,) = join_events([stock], [fifth])
    actual = dict(
        scheduled,
        released_ns=101,
        started_ns=102,
        emitted_ns=110,
        outcome="emitted",
        policy="stock",
        outstanding_at_admission=1,
        actual_sha256=stock["full_visit_sha256"],
    )
    validate_event(actual, scheduled, "adaptive")
    with pytest.raises(ValueError, match="selected detector"):
        validate_event(
            dict(actual, actual_sha256=fifth["full_visit_sha256"]), scheduled, "adaptive"
        )
    with pytest.raises(ValueError, match="causal admission"):
        validate_event(dict(actual, outstanding_at_admission=0), scheduled, "adaptive")


def test_join_rejects_branch_clock_mismatch_and_hardware_exclusion_difference():
    stock, fifth = events()
    with pytest.raises(ValueError, match="same physical"):
        join_events([stock], [dict(fifth, sample_start=302)])
    stock, fifth = events("invalid_capture")
    with pytest.raises(ValueError, match="hardware exclusion"):
        join_events([stock], [fifth])
