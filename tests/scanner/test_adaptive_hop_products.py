"""Bounded full-300-s metadata scale; no claim that these fixtures contain IQ."""

import pytest

from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisConfigurationV1
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
    AdaptiveHopVisitReferenceV1,
)
from tests.scanner.adaptive_hop_fixtures import receipt_fixture


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_full_300s_metadata_manifest_closes_every_actual_visit_without_sweeps(rate, mode):
    receipt = receipt_fixture(rate=rate, mode=mode, complete=True)
    cfg = AdaptiveHopAnalysisConfigurationV1(sample_rate_hz=rate)
    digest = "sha256:" + "1" * 64
    binding = AdaptiveHopAnalysisBindingV1(
        receipt=receipt, input_manifest_sha256=digest, configuration=cfg
    )
    geometry = receipt.plan.geometry
    hop_samples = geometry.valid_visit_samples + geometry.transition_guard_samples + 20
    assert (
        receipt.complete_visit_count
        == (geometry.nominal_device_sample_count + hop_samples - 1) // hop_samples
    )
    assert (
        geometry.nominal_device_sample_count
        <= receipt.duty_denominator_sample_count
        < geometry.nominal_device_sample_count + hop_samples
    )
    references = tuple(
        AdaptiveHopVisitReferenceV1(
            visit_index=i,
            relative_path=f"visit-{i:06d}.v1.json.zst",
            compressed_sha256=digest,
            uncompressed_sha256=digest,
            compressed_bytes=100,
            uncompressed_bytes=200,
            probe_count=22,
            candidate_count=0,
            fractional_candidate_count=0,
            passed_fractional_candidate_count=0,
        )
        for i in range(receipt.complete_visit_count)
    )
    manifest = AdaptiveHopMetricsManifestV1(
        session_id=receipt.session_id,
        input_manifest_sha256=digest,
        binding_sha256=binding.sha256,
        configuration=cfg,
        complete_visit_count=receipt.complete_visit_count,
        visits=references,
        finalized_utc_ns=1,
    )
    assert len(manifest.model_dump_json()) < 4 * 1024 * 1024
    assert AdaptiveHopMetricsManifestV1.model_validate_json(manifest.model_dump_json()) == manifest
    assert len(binding.model_dump_json()) < 32 * 1024 * 1024
    assert AdaptiveHopAnalysisBindingV1.model_validate_json(binding.model_dump_json()) == binding
    for changes in (
        {"visits": references[:-1]},
        {"visits": tuple(reversed(references))},
        {"complete_visit_count": 0},
    ):
        with pytest.raises(ValueError):
            AdaptiveHopMetricsManifestV1.model_validate({**manifest.model_dump(), **changes})
