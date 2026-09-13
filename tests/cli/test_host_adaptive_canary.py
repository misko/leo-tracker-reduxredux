from threading import Event
from types import SimpleNamespace as N

import pytest

from tools.run_host_adaptive_canary import qualify_result


@pytest.mark.parametrize(
    "fault", [None, "duty", "health", "delivery", "fallback", "deadline", "capture"]
)
def test_live_gate_never_qualifies_degraded_capture_or_policy(fault):
    result = N(capture_qualified=fault != "capture")
    receipt = N(
        valid_duty_ppm=949999 if fault == "duty" else 954000,
        host_decisions=[
            N(
                health="queue_overflow" if fault == "health" else "healthy",
                feedback_disposition="rejected" if fault == "delivery" else "accepted",
            ),
            N(health="healthy", feedback_disposition="source_ended"),
        ],
    )
    detail = N(capture=N(fallback_choices=int(fault == "fallback")))
    cancel = Event()
    if fault == "deadline":
        cancel.set()
    if fault:
        with pytest.raises(ValueError):
            qualify_result(result, receipt, detail, cancel)
    else:
        qualify_result(result, receipt, detail, cancel)
