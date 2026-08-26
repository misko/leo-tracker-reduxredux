from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from leo.contracts.digests import canonical_digest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "reports/figures/2026_08_26_final_doppler_holdout_attempt2"
PACKAGING_MANIFEST = ARTIFACT_DIRECTORY / "pre-response-packaging-manifest.json"


def _sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return "sha256:" + digest.hexdigest(), size


def test_lossless_rankings_package_reconstructs_exact_raw_authority() -> None:
    manifest = json.loads(PACKAGING_MANIFEST.read_text())
    assert manifest["manifest_digest"] == canonical_digest(
        {key: value for key, value in manifest.items() if key != "manifest_digest"}
    )
    package = manifest["lossless_packaging"]
    assert package["generation_zstd_version"] == "1.5.7"
    assert package["compression_level"] == 19
    assert package["worker_count"] == 1
    assert package["media_type"] == "application/zstd"
    assert package["determinism_pass_count"] == 2
    assert package["determinism_passes_byte_identical"] is True
    assert package["determinism_pass_1_sha256"] == package["compressed_sha256"]
    assert package["determinism_pass_2_sha256"] == package["compressed_sha256"]
    assert package["determinism_pass_1_byte_size"] == package["compressed_byte_size"]
    assert package["determinism_pass_2_byte_size"] == package["compressed_byte_size"]
    assert package["split_required"] is False
    assert package["parts"] == []
    assert package["compressed_byte_size"] < package["split_threshold_bytes"]

    compressed = ARTIFACT_DIRECTORY / package["compressed_basename"]
    assert _sha256_and_size(compressed) == (
        package["compressed_sha256"],
        package["compressed_byte_size"],
    )
    version = subprocess.run(
        ["zstd", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert version.strip()
    subprocess.run(
        ["zstd", "--test", "--no-progress", str(compressed)],
        check=True,
        capture_output=True,
    )

    process = subprocess.Popen(
        ["zstd", "--decompress", "--stdout", str(compressed)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    digest = hashlib.sha256()
    reconstructed_size = 0
    for block in iter(lambda: process.stdout.read(1 << 20), b""):
        digest.update(block)
        reconstructed_size += len(block)
    assert process.stderr is not None
    stderr = process.stderr.read()
    assert process.wait() == 0, stderr.decode(errors="replace")
    assert "sha256:" + digest.hexdigest() == package["raw_sha256"]
    assert reconstructed_size == package["raw_byte_size"]

    raw = ARTIFACT_DIRECTORY / package["raw_basename"]
    if raw.exists():
        assert _sha256_and_size(raw) == (package["raw_sha256"], package["raw_byte_size"])


def test_packaging_manifest_binds_all_pre_response_artifacts_and_no_odd_access() -> None:
    manifest = json.loads(PACKAGING_MANIFEST.read_text())
    artifacts = manifest["artifacts"]
    for key in ("prediction_ledger", "association_bins", "pre_response_receipt"):
        binding = artifacts[key]
        assert _sha256_and_size(ARTIFACT_DIRECTORY / binding["basename"]) == (
            binding["sha256"],
            binding["byte_size"],
        )
    log_path = REPOSITORY_ROOT / manifest["execution"]["combined_command_output_path"]
    assert _sha256_and_size(log_path) == (
        manifest["execution"]["combined_command_output_sha256"],
        manifest["execution"]["combined_command_output_byte_size"],
    )
    receipt = json.loads((ARTIFACT_DIRECTORY / "pre-response-receipt.json").read_text())
    assert receipt["receipt_digest"] == artifacts["pre_response_receipt"]["semantic_digest"]
    assert receipt["protocol_sha256"] == manifest["protocol"]["sha256"]
    assert receipt["protocol_digest"] == manifest["protocol"]["semantic_digest"]
    assert receipt["prediction_ledger_digest"] == artifacts["prediction_ledger"]["semantic_digest"]
    assert receipt["artifacts"]["prediction_ledger"] == {
        "basename": artifacts["prediction_ledger"]["basename"],
        "sha256": artifacts["prediction_ledger"]["sha256"],
        "semantic_digest": artifacts["prediction_ledger"]["semantic_digest"],
    }
    assert receipt["artifacts"]["association_bins"] == {
        "basename": artifacts["association_bins"]["basename"],
        "sha256": artifacts["association_bins"]["sha256"],
        "semantic_digest": artifacts["association_bins"]["semantic_digest"],
    }
    assert receipt["artifacts"]["rankings_and_controls"] == {
        "basename": artifacts["rankings_and_controls_raw"]["basename"],
        "sha256": artifacts["rankings_and_controls_raw"]["sha256"],
        "semantic_digest": artifacts["rankings_and_controls_raw"]["semantic_digest"],
    }
    assert receipt["odd_iq_accessed"] is False
    assert receipt["odd_responses_accessed"] is False
    assert manifest["execution"]["odd_iq_accessed"] is False
    assert manifest["execution"]["odd_responses_accessed"] is False
