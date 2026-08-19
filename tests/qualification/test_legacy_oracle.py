from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest
from leo.contracts.scientific import PilotDecisionStatus, PilotWindowDecisionV1
from leo.qualification.legacy_oracle import (
    LEGACY_ACQUISITION_SOURCE_SHA256,
    LEGACY_ANALYSIS_SOURCE_SHA256,
    LEGACY_DECODE_SOURCE_SHA256,
    LEGACY_REVISION,
    LEGACY_UV_LOCK_SHA256,
    LegacyOracleConfigV1,
    LegacyOracleReceiptV1,
    _safe_input_file,
    _seal_worker_payload,
    load_sealed_legacy_decisions,
)


def _config() -> LegacyOracleConfigV1:
    values = {
        "schema_version": 1,
        "source_revision": LEGACY_REVISION,
        "source_tree": "1" * 40,
        "uv_lock_sha256": LEGACY_UV_LOCK_SHA256,
        "acquisition_source_sha256": LEGACY_ACQUISITION_SOURCE_SHA256,
        "analysis_source_sha256": LEGACY_ANALYSIS_SOURCE_SHA256,
        "decode_source_sha256": LEGACY_DECODE_SOURCE_SHA256,
        "worker_sha256": f"sha256:{'2' * 64}",
        "legacy_python_sha256": f"sha256:{'4' * 64}",
        "required_environment_fingerprint_sha256": _environment()[
            "environment_fingerprint_sha256"
        ],
        "sample_rate_hz": 2_500_000,
        "dwell_sample_count": 150_000_000,
        "window_sample_count": 25_000,
        "interval_sample_count": 250_000,
        "scheduled_window_count": 600,
        "input_format": "ci16_le_interleaved_iq_single_receiver",
        "normalization": "complex64(I+jQ)/32768",
        "edge": "lower",
        "acquisition_method": "pilot_symbolwise_v3",
        "acquisition_span_hz": 0.0,
        "acquisition_step_hz": 500_000.0,
        "exact_subband_rate_hz": 2_500_000.0,
        "single_match_margin": 0.025,
        "single_symbol_margin": 0.03,
        "cfo_semantics": "absolute_digital_offset_hz",
        "receiver_center_hz": -162_048.5,
    }
    return LegacyOracleConfigV1(**values, config_digest=canonical_digest(values))


def _decisions() -> list[dict[str, object]]:
    decisions = []
    for index in range(600):
        decision = PilotWindowDecisionV1.create(
            source="legacy_reference",
            algorithm_id="leo-tracker-pilot-symbolwise-v3-single-rx",
            algorithm_version=LEGACY_REVISION,
            window_iq_digest=f"sha256:{index:064x}",
            window_index=index,
            sample_start=index * 250_000,
            status=PilotDecisionStatus.EVALUATED,
            candidate=False,
            reason="historical single-RX candidate gates did not pass",
        )
        decisions.append(decision.model_dump(mode="json"))
    return decisions


def _environment() -> dict[str, object]:
    values: dict[str, object] = {
        "schema_version": 1,
        "python_executable": "/qualification/legacy/bin/python",
        "python_sha256": f"sha256:{'4' * 64}",
        "python_version": "3.11.16",
        "numpy_version": "2.4.6",
        "scipy_version": "1.17.1",
        "installed_distributions": ["leo-tracker==0.1.0", "numpy==2.4.6", "scipy==1.17.1"],
    }
    return {**values, "environment_fingerprint_sha256": canonical_digest(values)}


def test_worker_payload_is_sealed_and_loadable(tmp_path: Path) -> None:
    iq = tmp_path / "input.ci16"
    iq.write_bytes(b"")
    config = _config()
    payload = {
        "config_digest": config.config_digest,
        "iq_sha256": f"sha256:{'3' * 64}",
        "environment": _environment(),
        "decisions": _decisions(),
    }
    receipt = _seal_worker_payload(
        payload, iq=iq, iq_sha256=f"sha256:{'3' * 64}", config=config
    )
    assert len(receipt.decisions) == 600
    assert receipt.decisions[599].sample_start == 149_750_000

    path = tmp_path / "receipt.json"
    path.write_text(receipt.model_dump_json(), encoding="utf-8")
    assert load_sealed_legacy_decisions(path) == receipt.decisions


def test_receipt_rejects_missing_or_reordered_decisions(tmp_path: Path) -> None:
    iq = tmp_path / "input.ci16"
    iq.write_bytes(b"")
    config = _config()
    payload = {
        "config_digest": config.config_digest,
        "iq_sha256": f"sha256:{'3' * 64}",
        "environment": _environment(),
        "decisions": _decisions(),
    }
    receipt = _seal_worker_payload(
        payload, iq=iq, iq_sha256=f"sha256:{'3' * 64}", config=config
    )
    document = receipt.model_dump(mode="json")
    document["decisions"] = document["decisions"][:-1]
    document["receipt_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "receipt_digest"}
    )
    with pytest.raises(ValueError, match="exactly 600"):
        LegacyOracleReceiptV1.model_validate(document)


def test_receipt_digest_detects_tampering(tmp_path: Path) -> None:
    iq = tmp_path / "input.ci16"
    iq.write_bytes(b"")
    config = _config()
    payload = {
        "config_digest": config.config_digest,
        "iq_sha256": f"sha256:{'3' * 64}",
        "environment": _environment(),
        "decisions": _decisions(),
    }
    receipt = _seal_worker_payload(
        payload, iq=iq, iq_sha256=f"sha256:{'3' * 64}", config=config
    )
    document = receipt.model_dump(mode="json")
    document["iq_path"] = "/different/input.ci16"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="receipt digest"):
        load_sealed_legacy_decisions(path)


def test_input_symlink_is_rejected_without_following_target(tmp_path: Path) -> None:
    link = tmp_path / "iq.ci16"
    link.symlink_to("/mnt/qnap01/forbidden.ci16")
    with pytest.raises(ValueError, match="symlink"):
        _safe_input_file(link, "IQ input")


def test_current_package_never_imports_legacy_runtime() -> None:
    package_root = Path(__file__).parents[2] / "src" / "leo"
    imports = []
    for path in package_root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(("from leo_tracker", "import leo_tracker")):
                imports.append(f"{path}:{line}")
    assert imports == []


def test_worker_emits_absolute_acquisition_cfo_not_qam_residual() -> None:
    worker = runpy.run_path(
        str(Path(__file__).parents[2] / "tools" / "legacy_oracle_worker.py"),
        run_name="legacy_oracle_worker_test",
    )
    result = {
        "pilot": {
            "frequency_offset_hz": -194_343.874,
            "local_frequency_offset_hz": -204_343.874,
            "residual_cfo_refinement_hz": -1.2784,
        },
        "acquisition": {"selected_center_offset_hz": 10_000.0},
    }
    assert worker["_absolute_cfo"](result) == pytest.approx(-194_343.874)
    result["pilot"]["frequency_offset_hz"] = -194_000.0
    with pytest.raises(ValueError, match="absolute CFO semantics"):
        worker["_absolute_cfo"](result)
