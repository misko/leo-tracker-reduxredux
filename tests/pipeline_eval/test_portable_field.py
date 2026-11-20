from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.qualification import portable_field_run
from tools.pipeline_eval.variants import portable_field


@pytest.fixture(scope="module")
def binary(tmp_path_factory):
    return portable_field_run.build(tmp_path_factory.mktemp("portable-field"))["binary"]["path"]


def window(edge, active):
    samples = np.zeros((200_000, 2, 2), dtype="<i2")
    frame = qin_edge_pilot_frame(10_000_000, edge)
    for receiver in active:
        for i in range(14):
            first = (40_000 * i + 1) // 3 + 2_000
            region = samples[first : first + len(frame), receiver]
            region[:, 0] = np.round(frame.real * 3000)
            region[:, 1] = np.round(frame.imag * 3000)
    return SimpleNamespace(
        samples=samples,
        sample_rate_hz=10_000_000,
        target={"rf_center_hz": 10_710_000_000, "lnb_lo_hz": 9_750_000_000, "edge": edge},
        acquisition={"actual_if_center_hz": 960_000_000},
    )


@pytest.mark.hardware
@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_gate_controls_partner_retry_and_preserves_public_rank(binary, edge):
    with portable_field.Detector(binary, edge) as detector:
        dual = detector(window(edge, (0, 1)), (0, 1))
        assert [(g["lane"], g["anchors"], g["published"]) for g in detector.attempts] == [
            (0, 12, True),
            (1, 12, True),
        ]
        for received in dual:
            peak = received.candidates[0]
            assert peak.candidate_rank == 0
            assert abs(peak.fractional_tracking_cfo_hz) < 10
            assert abs(peak.fractional_frame_phase_sample - 2_000) < 0.5
            assert peak.fractional_margin > 0.5
        single = detector(window(edge, (0,)), (0, 1))
        assert [(g["lane"], g["anchors"], g["published"]) for g in detector.attempts] == [
            (0, 12, True),
            (1, 12, False),
            (1, 22, True),
        ]
        assert single[0] == dual[0]
        assert single[1].receiver_id == 1 and single[1].candidates == ()
        empty = detector(window(edge, ()), (0, 1))
        assert len(detector.attempts) == 2
        assert [r.candidates for r in empty] == [(), ()]


@pytest.mark.hardware
def test_rejects_incomplete_payload_before_native_access(binary):
    incomplete = window("lower", ())
    incomplete.samples = incomplete.samples[:-1]
    with (
        portable_field.Detector(binary, "lower") as detector,
        pytest.raises(ValueError, match="CI16"),
    ):
        detector(incomplete, (0, 1))


def test_raw_timeout_retains_verified_chunks_and_withholds_position(tmp_path, monkeypatch):
    (tmp_path / "source-lock.json").write_text("{}\n")
    lock = {
        "workers": [(0, 8, [(0, 0, 4, 0), (0, 4, 8, 0)])],
        "recording": {"window_count": 8},
        "raw_limit_s": 600,
        "smoke": False,
    }
    closed = {
        (0, 0): (
            {},
            [
                dict(
                    visit=i,
                    status="processed",
                    detector_cpu_s=0.1,
                    detector_wall_s=0.1,
                    grid_calls=2,
                )
                for i in range(4)
            ],
        )
    }
    timeout = {"exit_code": 1, "systemd": {"Result": "timeout"}}
    monkeypatch.setattr(portable_field_run.original, "service", lambda *_: timeout)
    monkeypatch.setattr(portable_field_run.original, "collect", lambda *_: (closed, {}, 1.0))
    monkeypatch.setattr(portable_field_run.iq_service, "succeeded", lambda _: False)

    def unexpected_fit(*_):
        pytest.fail("position fitting received an incomplete recording")

    monkeypatch.setattr(portable_field_run.original, "fit", unexpected_fit)
    summary = portable_field_run.run(tmp_path, lock)
    assert summary["status"] == "timed_out"
    assert summary["stage"] == "raw"
    assert summary["completed_visits"] == 4
    assert summary["scheduled_visits"] == 8
    assert summary["completed_chunks"] == 1
    assert "result" not in summary
