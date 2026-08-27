from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from leo.contracts.digests import canonical_digest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/run_satellite_pnt_long_arc_development.py"
PROTOCOL_PATH = ROOT / "config/analysis/satellite-pnt-long-arc-development-protocol-v1.json"
TLE_9981 = Path("/tmp/cap-20260824-space-track-causal.tle")
TLE_150802 = Path("/tmp/cap-20260825-space-track-causal.tle")
FAILED_RECEIPT = ROOT / (
    "reports/figures/2026_08_27_satellite_pnt_long_arc_development_attempt1-execution-receipt.json"
)


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "satellite_pnt_long_arc_execution_tool", TOOL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _document() -> dict[str, Any]:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    commit = _git("rev-parse", "HEAD")
    implementation_hashes = {
        relative: _sha256(ROOT / relative) for relative in tool._IMPLEMENTATION_FILES
    }
    payload: dict[str, Any] = {
        "schema": "org.leo.research.satellite-pnt-long-arc-execution-amendment/v1",
        "amendment_id": "synthetic-validation-only",
        "status": "frozen-authority-for-one-opened-development-execution",
        "chronology": "test-only authority document; no execution",
        "base_protocol": {
            "path": PROTOCOL_PATH.relative_to(ROOT).as_posix(),
            "sha256": _sha256(PROTOCOL_PATH),
            "protocol_digest": protocol["protocol_digest"],
        },
        "implementation": {
            "commit": commit,
            "tree": _git("rev-parse", f"{commit}^{{tree}}"),
            "file_sha256": implementation_hashes,
        },
        "raw_tle_inputs": [
            {
                "arc_id": "long-arc-9981-r19f2-s1-rx1-upper-0-30s",
                "path": str(TLE_9981),
                "sha256": _sha256(TLE_9981),
                "object_count": 10972,
            },
            {
                "arc_id": "long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s",
                "path": str(TLE_150802),
                "sha256": _sha256(TLE_150802),
                "object_count": 10972,
            },
        ],
        "numerical_controls": {
            "tau_lower_s": -5.0,
            "tau_upper_s": 5.0,
            "tau_step_s": 0.25,
            "tau_state_count": 41,
            "support_integration_sample_count": 5,
            "prediction_uncertainty_floor_hz": 1.0,
            "prediction_element_age_growth_hz_per_day": 0.0,
            "prediction_fit_residual_multiplier": 1.0,
            "prediction_maximum_propagated_states": 250000000,
            "population_coarse_spacing_s": 0.1,
            "population_maximum_coarse_time_count": 10000,
            "population_maximum_exact_time_count": 200000,
            "population_maximum_coarse_propagated_states": 10000000,
            "population_maximum_exact_propagated_states": 20000000,
            "maximum_candidate_count": 10000,
            "partition_rounding": "nearest-integer-half-up-v1",
        },
        "outputs": {
            "artifact_directory": "reports/figures/__satellite_pnt_execution_test_absent__",
            "attempt_receipt_path": (
                "reports/figures/__satellite_pnt_execution_test_absent_receipt__.json"
            ),
            "report_path": "reports/__satellite_pnt_execution_test_absent__.md",
        },
        "execution": {
            "authorized": True,
            "maximum_attempt_count": 1,
            "attempt_number": 1,
            "outputs_must_not_exist_before_execution": True,
            "response_scoring_before_this_amendment": False,
            "new_rf_collection_authorized": False,
        },
        "claim_boundary": {
            "opened_development_only": True,
            "secure_norad_permitted": False,
            "positioning_validation_permitted": False,
            "wrong_epoch_is_null_distribution": False,
            "wrong_epoch_is_gate": False,
            "numerical_thresholds_are_set": False,
            "new_rf_collection_authorized": False,
        },
    }
    return {**payload, "amendment_digest": canonical_digest(payload)}


def _write(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "amendment.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def _retry_document() -> dict[str, Any]:
    payload = _document()
    payload.pop("amendment_digest")
    payload.update(
        {
            "schema": "org.leo.research.satellite-pnt-long-arc-execution-amendment/v2",
            "amendment_id": "synthetic-retry-validation-only",
            "status": ("frozen-authority-for-one-opened-development-retry-after-work-cap-failure"),
            "chronology": "test-only retry authority; no execution",
            "predecessor_attempt": {
                "path": FAILED_RECEIPT.relative_to(ROOT).as_posix(),
                "sha256": _sha256(FAILED_RECEIPT),
                "attempt_number": 1,
                "status": "failed",
                "exception_type": "CataloguePopulationWorkLimitError",
                "exception_message": (
                    "exact Starlink population exceeds the declared propagation cap"
                ),
                "prior_amendment_digest": (
                    "sha256:5f90039ae688027978fe23284cd7b64bb8a1ba7082ae1fc4f08f2d707f8c43ce"
                ),
            },
            "work_cap_amendment": {
                "failure_layer": "response-free-field-population-work-cap",
                "failing_arc_id": ("long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s"),
                "failing_field_delta_s": -500,
                "previous_maximum_exact_propagated_states": 20000000,
                "response_free_diagnostic_counts": [
                    {
                        "arc_id": "long-arc-9981-r19f2-s1-rx1-upper-0-30s",
                        "field_delta_s": -500,
                        "exact_time_count": 4701,
                        "coarse_candidate_count": 510,
                        "exact_work": 2397510,
                    },
                    {
                        "arc_id": "long-arc-9981-r19f2-s1-rx1-upper-0-30s",
                        "field_delta_s": 0,
                        "exact_time_count": 4701,
                        "coarse_candidate_count": 490,
                        "exact_work": 2303490,
                    },
                    {
                        "arc_id": "long-arc-9981-r19f2-s1-rx1-upper-0-30s",
                        "field_delta_s": 500,
                        "exact_time_count": 4701,
                        "coarse_candidate_count": 504,
                        "exact_work": 2369304,
                    },
                    {
                        "arc_id": ("long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s"),
                        "field_delta_s": -500,
                        "exact_time_count": 50361,
                        "coarse_candidate_count": 576,
                        "exact_work": 29007936,
                    },
                    {
                        "arc_id": ("long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s"),
                        "field_delta_s": 0,
                        "exact_time_count": 50361,
                        "coarse_candidate_count": 579,
                        "exact_work": 29159019,
                    },
                    {
                        "arc_id": ("long-arc-150802-r19f2-s1-rx1-upper-37p575-51p4s"),
                        "field_delta_s": 500,
                        "exact_time_count": 50361,
                        "coarse_candidate_count": 578,
                        "exact_work": 29108658,
                    },
                ],
                "maximum_observed_exact_work": 29159019,
                "replacement_maximum_exact_propagated_states": 30000000,
                "scientific_model_changed": False,
                "response_scores_used_for_diagnosis": False,
            },
        }
    )
    payload["numerical_controls"]["population_maximum_exact_propagated_states"] = 30000000
    payload["outputs"] = {
        "artifact_directory": "reports/figures/__satellite_pnt_retry_test_absent__",
        "attempt_receipt_path": (
            "reports/figures/__satellite_pnt_retry_test_absent_receipt__.json"
        ),
        "report_path": "reports/__satellite_pnt_retry_test_absent__.md",
    }
    payload["execution"] = {
        "authorized": True,
        "maximum_attempt_count": 2,
        "attempt_number": 2,
        "outputs_must_not_exist_before_execution": True,
        "response_scoring_before_this_amendment": True,
        "new_rf_collection_authorized": False,
    }
    return {**payload, "amendment_digest": canonical_digest(payload)}


def test_amendment_validation_closes_protocol_code_tles_and_outputs(
    tmp_path: Path,
) -> None:
    document = _document()

    validated = tool.validate_execution_amendment(ROOT, _write(tmp_path, document))

    assert validated["amendment_digest"] == document["amendment_digest"]
    assert tuple(sorted(validated["implementation"]["file_sha256"])) == (tool._IMPLEMENTATION_FILES)
    assert validated["execution"]["maximum_attempt_count"] == 1
    assert validated["claim_boundary"]["secure_norad_permitted"] is False


def test_amendment_rejects_code_or_output_substitution(
    tmp_path: Path,
) -> None:
    document = _document()
    hashes = document["implementation"]["file_sha256"]
    first = next(iter(hashes))
    hashes[first] = "sha256:" + "0" * 64
    payload = {key: value for key, value in document.items() if key != "amendment_digest"}
    with pytest.raises(tool.LongArcExecutionAuthorityError, match="implementation file drifted"):
        tool.validate_execution_amendment(
            ROOT,
            _write(tmp_path, {**payload, "amendment_digest": canonical_digest(payload)}),
        )


def test_retry_amendment_binds_failure_and_changes_only_the_work_cap(
    tmp_path: Path,
) -> None:
    document = _retry_document()

    validated = tool.validate_execution_amendment(ROOT, _write(tmp_path, document))
    assert validated["execution"]["attempt_number"] == 2
    assert validated["work_cap_amendment"]["maximum_observed_exact_work"] == 29159019
    assert validated["numerical_controls"]["population_maximum_exact_propagated_states"] == 30000000

    document["work_cap_amendment"]["scientific_model_changed"] = True
    payload = {key: value for key, value in document.items() if key != "amendment_digest"}
    with pytest.raises(tool.LongArcExecutionAuthorityError, match="work-cap-only"):
        tool.validate_execution_amendment(
            ROOT,
            _write(tmp_path, {**payload, "amendment_digest": canonical_digest(payload)}),
        )

    document = _document()
    document["outputs"]["artifact_directory"] = "plans"
    payload = {key: value for key, value in document.items() if key != "amendment_digest"}
    with pytest.raises(tool.LongArcExecutionAuthorityError, match="already exists"):
        tool.validate_execution_amendment(
            ROOT,
            _write(tmp_path, {**payload, "amendment_digest": canonical_digest(payload)}),
        )


def test_duplicate_keys_and_preflight_failure_stop_before_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write(tmp_path, _document())
    duplicate = path.read_text(encoding="utf-8").replace(
        '"amendment_id": "synthetic-validation-only",',
        '"amendment_id": "synthetic-validation-only",\n'
        '  "amendment_id": "synthetic-validation-only",',
        1,
    )
    path.write_text(duplicate, encoding="utf-8")
    with pytest.raises(tool.LongArcExecutionAuthorityError, match="duplicate JSON key"):
        tool.validate_execution_amendment(ROOT, path)

    monkeypatch.setattr(
        tool,
        "validate_execution_amendment",
        lambda root, amendment: (_ for _ in ()).throw(
            tool.LongArcExecutionAuthorityError("preflight stopped")
        ),
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("scientific runner started after failed preflight")

    monkeypatch.setattr(tool, "load_satellite_pnt_long_arc_protocol", forbidden)
    with pytest.raises(tool.LongArcExecutionAuthorityError, match="preflight stopped"):
        tool.execute_authorized_development_run(ROOT, path)


def test_attempt_is_sealed_and_failure_receipt_prevents_silent_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document()
    document["outputs"] = {
        "artifact_directory": "artifacts",
        "attempt_receipt_path": "attempt-receipt.json",
        "report_path": "report.md",
    }
    monkeypatch.setattr(tool, "validate_execution_amendment", lambda root, path: document)
    monkeypatch.setattr(tool, "_git", lambda root, *args: "a" * 40)

    def failed_execution(**kwargs: object) -> object:
        raise RuntimeError("synthetic execution failure")

    monkeypatch.setattr(tool, "_execute_after_attempt_seal", failed_execution)
    with pytest.raises(RuntimeError, match="synthetic execution failure"):
        tool.execute_authorized_development_run(tmp_path, tmp_path / "amendment.json")

    receipt = json.loads((tmp_path / "attempt-receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "failed"
    assert receipt["attempt_number"] == 1
    assert receipt["exception_type"] == "RuntimeError"
    assert receipt["exception_message"] == "synthetic execution failure"

    with pytest.raises(tool.LongArcExecutionAuthorityError, match="silent retry is forbidden"):
        tool.execute_authorized_development_run(tmp_path, tmp_path / "amendment.json")
