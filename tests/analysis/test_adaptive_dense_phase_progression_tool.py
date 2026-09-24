from __future__ import annotations

import math

from tools.report_adaptive_dense_phase_progression import associate, summarize


def _document(offsets: tuple[float, ...] = (-676_500.0,) * 5) -> dict[str, object]:
    visits = []
    for index, offset in enumerate(offsets):
        phase = math.radians(20.0 + 5.0 * index)
        visits.append(
            {
                "visit_index": 100 + 4 * index,
                "target_index": 3,
                "hypotheses": [
                    {
                        "low_rx0_tracking_cfo_hz": 400_000.0 - 2_000.0 * index,
                        "high_rx0_tracking_cfo_hz": 435_000.0 - 2_000.0 * index,
                        "alias_aware_signal_separation_hz": 35_000.0,
                        "receiver_offset_hz": offset,
                        "wrapped_high_minus_low_rad": phase,
                        "standard_error_rad": math.radians(2.0),
                        "common_session_time_s": 10.0 + 0.5 * index,
                        "phase_resultant_floor": 0.9,
                        "exact_to_control_power_ratio_floor": 8.0,
                    }
                ],
            }
        )
    return {
        "session_id": "scan-hop-0123456789abcdef",
        "input_manifest_sha256": "sha256:" + "1" * 64,
        "analysis_binding_sha256": "sha256:" + "2" * 64,
        "selected_visit_analyses_sha256": "sha256:" + "3" * 64,
        "probe_stride_ms": 10,
        "selected_visit_indexes": [row["visit_index"] for row in visits],
        "visits": visits,
    }


def test_association_does_not_read_phase_and_recovers_known_modulo_pi_slope() -> None:
    document = _document()
    paths = associate(document)
    assert len(paths) == 1
    assert len(paths[0]) == 5
    summary = summarize(document)
    metrics = summary["tracks"][0]["metrics"]
    assert math.isclose(metrics["conditional_modulo_pi_slope_deg_s"], 10.0, abs_tol=1e-10)
    assert metrics["pilot_phase_ambiguity"] == "modulo_pi"
    assert metrics["phase_continuity_across_retunes"] is False

    for visit in document["visits"]:
        visit["hypotheses"][0]["wrapped_high_minus_low_rad"] *= -1
        visit["hypotheses"][0]["phase_resultant_floor"] = 0.51
        visit["hypotheses"][0]["standard_error_rad"] *= 5
    assert [row.visit_index for row in associate(document)[0]] == [
        row.visit_index for row in paths[0]
    ]


def test_receiver_offset_alias_branch_is_not_joined() -> None:
    document = _document((-676_500.0, -676_500.0, -563_000.0, -563_000.0, -563_000.0))
    assert associate(document) == []
