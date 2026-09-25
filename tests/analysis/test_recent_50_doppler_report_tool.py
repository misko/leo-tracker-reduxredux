from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_recent_50_doppler_and_starlink.py"
    spec = importlib.util.spec_from_file_location("recent_50_doppler_report_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    result_root = tmp_path / "results"
    result_root.mkdir()
    inputs = []
    associations = []
    for index in range(1, 51):
        label = f"R{index:02d}"
        session_id = f"cap-20260823T{index:06d}-{index:012x}"
        run_id = f"run-{index}"
        analysis_digest = f"sha256:analysis-{index}"
        recording_digest = f"sha256:recording-{index}"
        inputs.append(
            {
                "label": label,
                "session_id": session_id,
                "run_id": run_id,
                "pipeline_release_id": "release-a",
                "analysis_manifest_digest": analysis_digest,
                "recording_manifest_digest": recording_digest,
            }
        )
        diagnostics = {
            "overall_glrt_rate_hz_s": -5_000.0,
            "overall_glrt_rate_sigma_hz_s": 5.0,
            "local_corrected_rate_hz_s": -3_000.0,
            "local_conditional_sigma_hz_s": 20.0,
            "local_practical_sigma_hz_s": 30.0,
            "local_p025_hz_s": -3_060.0,
            "local_p975_hz_s": -2_940.0,
            "rate_correction_hz_s": 2_000.0,
            "frame_count": 100,
            "qualified_frame_count": 80,
            "coherent_frame_count": 60,
            "ramp_count": 6,
            "strict_gate_rate_spread_hz_s": 40.0,
            "odd_validation_reduction_percent": 50.0,
            "glrt_rate_errors": {"validation_rms_hz": 60.0},
            "local_rate_errors": {"validation_rms_hz": 30.0, "frame_count": 60},
            "slope_progression_fit": {
                "slope_progression_hz_s2": -10.0,
                "slope_progression_sigma_hz_s2": 5.0,
            },
            "bic_progression_minus_common": 2.0,
        }
        result = {
            "schema": "org.leo.research.raw-dwell-doppler/v1",
            "session_id": session_id,
            "run_id": run_id,
            "analysis_manifest_digest": analysis_digest,
            "recording_manifest_digest": recording_digest,
            "status": "complete",
            "selected_attempt_rank": 1,
            "candidate_count": 3,
            "selected": {
                "candidate": {
                    "stream_id": "stream-0",
                    "receiver_id": 1,
                    "branch_id": f"branch-{index}",
                },
                "result": {
                    "diagnostics": diagnostics,
                    "ramps": [{"slope_hz_s": -3_000.0 + value} for value in range(6)],
                },
            },
        }
        suffix = session_id.rsplit("-", 1)[-1]
        (result_root / f"{label}-{suffix}.json").write_text(json.dumps(result), encoding="utf-8")
        best_identity = {
            "catalog_number": 10,
            "object_name": "STARLINK-10",
            "train_standardized_rms": 0.8,
            "holdout_standardized_rms": 0.9,
            "fitted_rate_nuisance_hz_s": 50.0,
        }
        ranked = {
            "rank": 1,
            "candidate": {
                "catalog_number": 10,
                "object_name": "STARLINK-10",
                "predicted_rate_hz_s": [-3_050.0] * 6,
            },
            "metrics": {
                "fitted_rate_nuisance_hz_s": 50.0,
                "train_standardized_rms": 0.8,
                "holdout_standardized_rms": 0.9,
                "nuisance_at_bound": False,
            },
        }
        associations.append(
            {
                "label": label,
                "session_id": session_id,
                "status": "complete",
                "radio_id": "radio-test",
                "primary_models": {
                    "bounded_200": {
                        "candidate_count": 4,
                        "ranked": [ranked],
                        "constant_rate_null": {"holdout_standardized_rms": 1.2},
                        "runner_up_train_standardized_margin": 0.4,
                    }
                },
                "association_sensitivity": {
                    "best_identity_by_rate_nuisance_model": {
                        "bounded_25": best_identity,
                        "bounded_200": best_identity,
                        "free": best_identity,
                    },
                    "broad_sky_control": {"best": best_identity},
                    "previous_complete_snapshot": {"available": True, "best": best_identity},
                    "following_complete_snapshot_noncausal_sensitivity_only": {
                        "available": True,
                        "best": best_identity,
                    },
                    "observer_site_provenance_stress": {
                        "directions": [{"best": best_identity} for _ in range(4)]
                    },
                },
                "best_candidate_error_budget": {
                    "timing_rate_effect_rms_hz_s": 2.0,
                    "site_max_rate_rms_hz_s": 0.1,
                    "rf_scale_max_rate_effect_hz_s": 0.3,
                    "finite_difference_rate_rms_hz_s": 0.02,
                    "previous_snapshot": {
                        "available": True,
                        "raw_rate_rms_hz_s": 4.0,
                        "constant_rate_nuisance_removed_rms_hz_s": 2.0,
                    },
                },
            }
        )
    inputs_path = tmp_path / "inputs.json"
    inputs_path.write_text(
        json.dumps({"selected_dwell_count": 50, "dwells": inputs}), encoding="utf-8"
    )
    associations_path = tmp_path / "associations.json"
    associations_path.write_text(
        json.dumps(
            {
                "dwells": associations,
                "observer": {
                    "latitude_deg": 37.0,
                    "longitude_deg": -122.0,
                    "altitude_m": 10.0,
                },
                "tle_authority_root": "/authority/tle",
                "tle_root": "/read-only-mirror/tle",
            }
        ),
        encoding="utf-8",
    )
    return inputs_path, result_root, associations_path


def test_report_aggregates_identity_closed_results_and_renders_figures(tmp_path: Path) -> None:
    tool = _tool()
    inputs, results, associations = _write_fixture(tmp_path)

    document, rows = tool.load_rows(inputs, results, associations)
    statistics = tool.aggregate(rows)

    assert len(rows) == 50
    assert statistics["raw_status_counts"] == {"complete": 50}
    assert statistics["pooled_glrt_odd_validation_rms_hz"] == pytest.approx(60.0)
    assert statistics["pooled_local_odd_validation_rms_hz"] == pytest.approx(30.0)
    assert statistics["association_assessment_counts"] == {"supported_candidate": 50}

    rate = tmp_path / "rates.png"
    match = tmp_path / "matches.png"
    errors = tmp_path / "errors.png"
    tool.render_rate_figure(rate, rows)
    tool.render_association_figure(match, rows)
    tool.render_error_budget(errors, statistics)
    for path in (rate, match, errors):
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    report = tmp_path / "report.md"
    tool.write_report(
        report,
        rows,
        statistics,
        document,
        summary_path=tmp_path / "summary.json",
        rate_figure=rate,
        association_figure=match,
        error_figure=errors,
    )
    text = report.read_text(encoding="utf-8")
    assert "50/50 produced" in text
    assert "0** have poor" in text
    assert "STARLINK-10 (10)" in text
