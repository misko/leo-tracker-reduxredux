from threading import Event
from types import SimpleNamespace as N

import pytest

import tools.run_host_adaptive_canary as canary
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


@pytest.mark.parametrize("failed", [False, True])
def test_capture_deadline_covers_startup_but_ends_before_offline_verification(monkeypatch, failed):
    calls = []

    class Timer:
        def __init__(self, duration, callback):
            assert duration == 335
            self.callback = callback

        def start(self):
            calls.append("armed")

        def cancel(self):
            calls.append("disarmed")

    def capture(intent, *, cancel):
        assert calls == ["armed"] and intent == "requested"
        assert not cancel.is_set()
        calls.append("capture")
        if failed:
            raise RuntimeError("capture failed")
        return "receipt"

    monkeypatch.setattr(canary, "Timer", Timer)
    backend = N(capture_scheduled_scanner=capture)
    if failed:
        with pytest.raises(RuntimeError, match="capture failed"):
            canary.capture_with_deadline(backend, "requested", Event())
    else:
        assert canary.capture_with_deadline(backend, "requested", Event()) == "receipt"
    assert calls == ["armed", "capture", "disarmed"]
