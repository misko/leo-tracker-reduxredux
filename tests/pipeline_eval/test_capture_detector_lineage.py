from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import capture_detector_lineage as study
from tools.pipeline_eval.qualification.capture_detector_replay import scan_capture_window


def test_capture_adapter_projects_original_candidate_ranks_and_gate(monkeypatch):
    from leo.scanner import fast_scan_analysis

    candidate = SimpleNamespace(
        candidate_rank=3,
        epoch_sample=173,
        fractional_epoch_status="complete",
        fractional_epoch_offset_samples=0.27,
        fractional_tracking_cfo_hz=314_720.0,
        fractional_exact_score=0.13,
        fractional_control_score=0.10,
        fractional_margin=0.03,
    )
    response = SimpleNamespace(
        status="processed",
        receivers=[
            SimpleNamespace(receiver_id=0, candidates=[candidate]),
            SimpleNamespace(receiver_id=1, candidates=[]),
        ],
    )
    monkeypatch.setattr(fast_scan_analysis, "analyze_window", lambda *_: response)
    window = SimpleNamespace(
        target={"channel": 1, "edge": "upper", "lnb_lo_hz": 10_000_000_000},
        acquisition={"global_visit": 5, "sample_start": 41, "actual_if_center_hz": 1_000_000},
        sample_rate_hz=10_000_000,
    )
    result, probes = scan_capture_window(window, (0, 1), object())
    assert result is response
    assert probes[0]["candidates"][0]["candidate_rank"] == 3
    assert probes[0]["candidates"][0]["passed_fractional_margin_gate"]
    assert probes[1]["candidates"] == []
    response.receivers.reverse()
    with pytest.raises(ValueError, match="reordered"):
        scan_capture_window(window, (0, 1), object())


def test_domain_intervention_preserves_original_cfo_geometry_elsewhere():
    @dataclass(frozen=True)
    class Geometry:
        residual_cfo_min_hz: float
        residual_cfo_max_hz: float
        step_hz: float = 80_000.0
        anchors: tuple[int, ...] = (2, 28)

    source = Geometry(-800_000.0, 800_000.0)
    narrowed = study.intersection(source, 72_051.5)
    assert narrowed == Geometry(-472_051.5, 327_948.5)
    assert source == Geometry(-800_000.0, 800_000.0)


def test_complete_projection_comparison_counts_negative_fields_and_fails_on_support_change():
    left = dict(
        visit_index=2,
        receiver_id=0,
        valid_start_counter=160,
        candidates=[{"fractional_margin": -0.012}],
    )
    right = dict(left, candidates=[{"fractional_margin": -0.013}])
    assert study.compare_rows([left], [right]) == dict(
        probes=1, exact=0, differing_fields={"fractional_margin": 1}, candidate_count=[1, 1]
    )
    with pytest.raises(ValueError, match="physical support"):
        study.compare_rows([left], [dict(right, valid_start_counter=161)])
