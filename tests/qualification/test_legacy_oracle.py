from __future__ import annotations

import fcntl
import hashlib
import json
import os
import runpy
import stat
import subprocess
from pathlib import Path

import pytest

import leo.qualification.legacy_oracle as legacy_oracle_module
from leo.contracts.digests import canonical_digest
from leo.contracts.scientific import PilotDecisionStatus, PilotWindowDecisionV1
from leo.qualification.legacy_oracle import (
    ENVIRONMENT_MANIFEST,
    ENVIRONMENT_MANIFEST_DIGEST,
    LEGACY_PYTHON,
    LEGACY_REVISION,
    LEGACY_ROOT,
    WORKER_PATH,
    LegacyOracleConfigV1,
    LegacyOracleEnvironmentV1,
    LegacyOracleReceiptV1,
    _acquire_qualification_lock,
    _atomic_create_confined,
    _frozen_config,
    _open_directory,
    _safe_input_file,
    _seal_worker_payload,
    _snapshot_iq,
    _verify_all_frozen_identities,
    load_sealed_legacy_decisions,
)

IQ_DIGEST = f"sha256:{'3' * 64}"
WORKER_OUTPUT_DIGEST = f"sha256:{'4' * 64}"


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


def _worker_payload(config: LegacyOracleConfigV1) -> dict[str, object]:
    manifest = json.loads(ENVIRONMENT_MANIFEST.read_text(encoding="utf-8"))
    return {
        "config_digest": config.config_digest,
        "iq_sha256": IQ_DIGEST,
        "environment": {
            "schema_version": 1,
            "manifest_digest": ENVIRONMENT_MANIFEST_DIGEST,
            "python_executable": str(LEGACY_PYTHON),
            "external_executable_files": manifest["external_executable_files"],
        },
        "decisions": _decisions(),
    }


def _receipt(tmp_path: Path) -> LegacyOracleReceiptV1:
    iq = tmp_path / "input.ci16"
    iq.write_bytes(b"")
    config = _frozen_config(-162_048.5)
    return _seal_worker_payload(
        _worker_payload(config),
        iq=iq,
        iq_sha256=IQ_DIGEST,
        config=config,
        worker_output_digest=WORKER_OUTPUT_DIGEST,
    )


def _publish(root: Path, name: str, receipt: LegacyOracleReceiptV1) -> None:
    root_fd = _open_directory(root)
    try:
        _atomic_create_confined(
            root_fd, name, receipt.model_dump_json().encode("utf-8") + b"\n"
        )
    finally:
        os.close(root_fd)


@pytest.mark.legacy_oracle
def test_frozen_identities_match_clean_reviewed_checkout() -> None:
    identities = _verify_all_frozen_identities()
    assert identities[0] == LEGACY_REVISION
    assert identities[3] == ENVIRONMENT_MANIFEST_DIGEST


@pytest.mark.legacy_oracle
def test_frozen_worker_protocol_imports_and_executes_historical_kernel(tmp_path: Path) -> None:
    _verify_all_frozen_identities()
    iq = tmp_path / "probe.ci16"
    payload = b"\0" * (25_000 * 4)
    iq.write_bytes(payload)
    iq_digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    values = {
        "schema_version": 1,
        "source_revision": LEGACY_REVISION,
        "legacy_root": str(LEGACY_ROOT),
        "environment_manifest_digest": ENVIRONMENT_MANIFEST_DIGEST,
        "sample_rate_hz": 2_500_000,
        "dwell_sample_count": 25_000,
        "window_sample_count": 25_000,
        "interval_sample_count": 250_000,
        "scheduled_window_count": 1,
        "edge": "lower",
        "acquisition_method": "pilot_symbolwise_v3",
        "acquisition_span_hz": 0.0,
        "acquisition_step_hz": 500_000.0,
        "exact_subband_rate_hz": 2_500_000.0,
        "single_match_margin": 0.025,
        "single_symbol_margin": 0.03,
        "receiver_center_hz": -162_048.5,
    }
    config = {**values, "config_digest": canonical_digest(values)}
    descriptor = os.open(iq, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        result = subprocess.run(
            [
                str(LEGACY_PYTHON),
                "-I",
                str(WORKER_PATH),
                "--iq-fd",
                str(descriptor),
                "--iq-sha256",
                iq_digest,
                "--config-json",
                json.dumps(config, sort_keys=True),
            ],
            cwd=LEGACY_ROOT,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "XDG_CACHE_HOME": str(tmp_path / "cache"),
            },
            check=True,
            capture_output=True,
            text=True,
            pass_fds=(descriptor,),
            timeout=300,
        )
    finally:
        os.close(descriptor)
    document = json.loads(result.stdout)
    LegacyOracleEnvironmentV1.model_validate(document["environment"])
    assert len(document["decisions"]) == 1
    decision = PilotWindowDecisionV1.model_validate(document["decisions"][0])
    assert decision.algorithm_version == LEGACY_REVISION
    assert decision.status is PilotDecisionStatus.EVALUATED


def test_worker_payload_is_sealed_published_and_loadable(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    assert len(receipt.decisions) == 600
    assert receipt.decisions[599].sample_start == 149_750_000
    _publish(tmp_path, "receipt.json", receipt)
    decisions = load_sealed_legacy_decisions(
        evidence_root=tmp_path, receipt_name="receipt.json"
    )
    assert decisions == receipt.decisions


def test_loader_rejects_handwritten_nonfrozen_publication(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    path = tmp_path / "receipt.json"
    path.write_text(receipt.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="publication semantics"):
        load_sealed_legacy_decisions(evidence_root=tmp_path, receipt_name=path.name)


def test_loader_rejects_0440_single_link_forged_decision_semantics(tmp_path: Path) -> None:
    document = _receipt(tmp_path).model_dump(mode="json")
    forged = PilotWindowDecisionV1.create(
        source="legacy_reference",
        algorithm_id="forged-legacy-lookalike",
        algorithm_version=LEGACY_REVISION,
        window_iq_digest=f"sha256:{0:064x}",
        window_index=0,
        sample_start=0,
        status=PilotDecisionStatus.EVALUATED,
        candidate=False,
        reason="forged result with internally valid content digest",
    )
    document["decisions"][0] = forged.model_dump(mode="json")
    document["receipt_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "receipt_digest"}
    )
    root_fd = _open_directory(tmp_path)
    try:
        _atomic_create_confined(
            root_fd,
            "forged.json",
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n",
        )
    finally:
        os.close(root_fd)
    forged_path = tmp_path / "forged.json"
    assert stat.S_IMODE(forged_path.stat().st_mode) == 0o440
    assert forged_path.stat().st_nlink == 1
    with pytest.raises(ValueError, match="exact frozen legacy kernel"):
        load_sealed_legacy_decisions(
            evidence_root=tmp_path, receipt_name=forged_path.name
        )


def test_config_rejects_arbitrary_worker_even_with_recomputed_digest() -> None:
    document = _frozen_config(-162_048.5).model_dump(mode="json")
    document["worker_path"] = "/tmp/arbitrary-worker.py"
    document["config_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "config_digest"}
    )
    with pytest.raises(ValueError, match="not v1"):
        LegacyOracleConfigV1.model_validate(document)


def test_receipt_rejects_missing_decision_with_recomputed_digest(tmp_path: Path) -> None:
    document = _receipt(tmp_path).model_dump(mode="json")
    document["decisions"] = document["decisions"][:-1]
    document["receipt_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "receipt_digest"}
    )
    with pytest.raises(ValueError, match="exact dwell and 600"):
        LegacyOracleReceiptV1.model_validate(document)


def test_receipt_digest_detects_tampering(tmp_path: Path) -> None:
    document = _receipt(tmp_path).model_dump(mode="json")
    document["iq_path"] = "/different/input.ci16"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    path.chmod(0o440)
    with pytest.raises(ValueError, match="receipt digest"):
        load_sealed_legacy_decisions(evidence_root=tmp_path, receipt_name=path.name)


def test_input_symlink_is_rejected_without_following_target(tmp_path: Path) -> None:
    link = tmp_path / "iq.ci16"
    link.symlink_to("/mnt/qnap01/forbidden.ci16")
    with pytest.raises(ValueError, match="symlink"):
        _safe_input_file(link, "IQ input")


def test_loader_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="one relative filename"):
        load_sealed_legacy_decisions(evidence_root=tmp_path, receipt_name="../receipt.json")


def test_iq_is_hashed_into_an_unlinked_stable_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = bytes(range(256)) * 16
    source = tmp_path / "input.ci16"
    source.write_bytes(payload)
    digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    monkeypatch.setattr(legacy_oracle_module, "IQ_BYTES", len(payload))
    root_fd = _open_directory(tmp_path)
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    snapshot_fd = None
    try:
        snapshot_fd = _snapshot_iq(root_fd, source_fd, digest)
        source.write_bytes(b"changed")
        assert os.pread(snapshot_fd, len(payload), 0) == payload
        snapshots = (
            item.name.startswith(".legacy-oracle-iq-snapshot") for item in tmp_path.iterdir()
        )
        assert not any(snapshots)
    finally:
        if snapshot_fd is not None:
            os.close(snapshot_fd)
        os.close(source_fd)
        os.close(root_fd)


def test_qualification_lock_is_exclusive_until_publication_scope_ends(
    tmp_path: Path,
) -> None:
    root_fd = _open_directory(tmp_path)
    first = _acquire_qualification_lock(root_fd)
    try:
        with pytest.raises(RuntimeError, match="qualification is active"):
            _acquire_qualification_lock(root_fd)
    finally:
        fcntl.flock(first, fcntl.LOCK_UN)
        os.close(first)
        os.close(root_fd)


def test_current_package_never_imports_legacy_runtime() -> None:
    package_root = Path(__file__).parents[2] / "src" / "leo"
    imports = []
    for path in package_root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(("from leo_tracker", "import leo_tracker")):
                imports.append(f"{path}:{line}")
    assert imports == []


def test_worker_emits_absolute_acquisition_cfo_not_qam_residual() -> None:
    worker = runpy.run_path(str(WORKER_PATH), run_name="legacy_oracle_worker_test")
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
