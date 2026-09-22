from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parents[2] / "reports" / "2026_09_22_blind_shared_orbit" / "render_validation.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("render_blind_shared_orbit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _document(module, coarse: Path) -> dict:
    result = {
        "shared_fit": {
            "episodes": [
                {"episode_id": "scan-a:track-1", "heldout_log_predictive": -8.0},
                {"episode_id": "scan-b:track-2", "heldout_log_predictive": -9.0},
            ]
        },
        "rate_corrections_s_h": {"100": 0.2, "200": -0.1},
        "recurrent_norad_episode_count": {"100": 3, "200": 1},
        "exact_replay_audits": [
            {"episode_id": "scan-a:track-1", "state": "complete", "maximum_error_hz": 0.01},
            {"episode_id": "scan-b:track-2", "state": "complete", "maximum_error_hz": 0.02},
        ],
    }
    nominal_result = {
        **result,
        "shared_fit": {
            "episodes": [
                {"episode_id": "scan-a:track-1", "heldout_log_predictive": -10.0},
                {"episode_id": "scan-b:track-2", "heldout_log_predictive": -8.5},
            ]
        },
    }
    document = {
        "schema": module.SCHEMA,
        "state": "complete",
        "truth_accessed": False,
        "provenance": {"coarse_result_sha256": module._digest_file(coarse)},
        "accounting": {"fit_track_count": 2},
        "protocol": {
            "global_resolution_status": "insufficient-no-whole-region-50km-search",
            "configuration": {"exact_audit_maximum_error_hz": 0.2},
        },
        "selected_nominal": {
            "latitude_deg": 38.0,
            "longitude_deg": -105.0,
            "matched_nominal_negative_log_posterior": 20.0,
        },
        "selected_shared": {
            "latitude_deg": 37.9,
            "longitude_deg": -104.9,
            "matched_shared_negative_log_posterior": 17.0,
        },
        "selected_nominal_result": nominal_result,
        "selected_shared_result": result,
        "outer_evaluations": [
            {
                "branch_id": "coarse-1",
                "latitude_deg": 38.0,
                "longitude_deg": -105.0,
                "matched_shared_negative_log_posterior": 18.0,
            },
            {
                "branch_id": "shared-final",
                "latitude_deg": 37.9,
                "longitude_deg": -104.9,
                "matched_shared_negative_log_posterior": 17.0,
            },
        ],
        "transfer_evaluation": {"state": "not-run"},
        "limitations": ["global resolution is insufficient"],
    }
    document["seal_sha256"] = module._digest_value(document)
    return document


def test_renders_only_digest_bound_sealed_result(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    coarse = tmp_path / "chronological-v2.json"
    coarse.write_text('{"state":"complete"}\n')
    sealed = tmp_path / "sealed.json"
    sealed.write_text(json.dumps(_document(module, coarse)))
    output = tmp_path / "rendered"
    monkeypatch.setattr(
        "sys.argv",
        [
            str(SCRIPT),
            "--sealed-result",
            str(sealed),
            "--coarse-result",
            str(coarse),
            "--output-dir",
            str(output),
            "--reference-latitude-deg",
            "37.85",
            "--reference-longitude-deg",
            "-122.48",
        ],
    )
    assert module.main() == 0
    summary = json.loads((output / "summary.json").read_text())
    assert summary["predictive"]["episode_count"] == 2
    assert summary["rate_and_audit"]["recurrent_norad_count"] == 1
    assert summary["rate_and_audit"]["exact_audit_pass"] is True
    assert len(list(output.glob("*.png"))) == 3

    corrupted = json.loads(sealed.read_text())
    corrupted["selected_shared"]["latitude_deg"] = 0.0
    sealed.write_text(json.dumps(corrupted))
    with pytest.raises(ValueError, match="seal"):
        module._load_sealed(sealed, coarse)


def test_rejects_excluded_randomized_coarse_path(tmp_path: Path) -> None:
    module = _module()
    coarse = tmp_path / module.EXCLUDED_COARSE_MARKER / "full-region-1000km.json"
    coarse.parent.mkdir()
    coarse.write_text("{}")
    sealed = tmp_path / "sealed.json"
    sealed.write_text(json.dumps(_document(module, coarse)))
    with pytest.raises(ValueError, match="excluded"):
        module._load_sealed(sealed, coarse)


def test_accepts_sealed_insufficient_scientific_state(tmp_path: Path) -> None:
    module = _module()
    coarse = tmp_path / "chronological-v2.json"
    coarse.write_text("{}")
    document = _document(module, coarse)
    document.pop("seal_sha256")
    document["state"] = "insufficient"
    document["seal_sha256"] = module._digest_value(document)
    sealed = tmp_path / "sealed.json"
    sealed.write_text(json.dumps(document))
    assert module._load_sealed(sealed, coarse)["state"] == "insufficient"
