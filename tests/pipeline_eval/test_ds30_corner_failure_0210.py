from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from ds30_corner_failure_0210 import CHAIN, NORMAL_SCOPE, OUTSIDE, charged_clock, corner_trace, support_disposition


def failure(frames):
    return "\n".join(["Traceback (most recent call last):", *(
        f'  File "/checked/{path}", line {line}, in {method}' for path,line,method in frames
    ), "ValueError: " + OUTSIDE])


def test_same_message_only_counts_with_the_exact_sparse_corner_and_retry_stack():
    separator = "\nDuring handling of the above exception, another exception occurred:\n"
    retry = (*CHAIN[:1], ("v5_orbit_domain.py", "159", "explore"), *CHAIN[1:])
    trace = failure(CHAIN) + separator + failure(retry)
    assert corner_trace(trace)["retry_reached_original_sparse_instance"]
    with pytest.raises(ValueError, match="sparse corner interpolation"):
        corner_trace(failure(CHAIN) + separator + failure(retry[:-2] + retry[-1:]))
    with pytest.raises(ValueError, match="second attempt"):
        corner_trace(failure(retry) + separator + failure(retry))


def test_nominal_support_cannot_be_mistaken_for_causal_extension_or_skipped_corners():
    nominal = dict(corner_projections_extended=0, added_knots_s=[], sgp4_calls=0, new_state_count=0,
                   sgp4_state_count=0, max_augmented_bank_bytes=0, support_wall_s=0.)
    route = dict(original_restart=[])
    extend = nominal | dict(corner_projections_extended=4, added_knots_s=list(range(-26,-17)),
                            sgp4_calls=4, new_state_count=1116, sgp4_state_count=1116)
    assert support_disposition(nominal, 4, route, "stock") == "original_nominal_support_used"
    assert support_disposition(extend, 4, route, "orbit_support") == "causal_extension_used"
    with pytest.raises(ValueError, match="ordinary corner"):
        support_disposition(nominal, 0, route, "stock")
    with pytest.raises(ValueError, match="zero live extension"):
        support_disposition(nominal | {"new_state_count": 1}, 4, route, "stock")


def test_failed_exit_stays_in_denominator_without_diagnostic_verifier_cost():
    process = dict(elapsed_s=10., cpu_s=8., timed_out=False, exit_code=1)
    original = dict(process=process, validation=dict(elapsed_s=.5, cpu_s=.4),
                    outcome="solver_failed", timing_scope="raw_launch_to_exit", elapsed_s=10., cpu_s=8.)
    assert charged_clock(original, process)["charged_wall_s"] == 10.
    assert not charged_clock(original, process)["verifier_charged"]
    success = original | dict(process=process | {"exit_code": 0}, outcome="complete", timing_scope=NORMAL_SCOPE,
                              elapsed_s=10.5, cpu_s=8.4)
    assert charged_clock(success, success["process"])["verifier_charged"]
    with pytest.raises(ValueError, match="verifier boundary"):
        charged_clock(success | {"elapsed_s": 10.}, success["process"])
