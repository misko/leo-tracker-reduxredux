from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from leo.contracts.arm_glrt import ArmGlrtCandidateV1, ArmGlrtConfigurationV1, ArmGlrtInputBindingV1
from leo.contracts.digests import sha256_digest
from leo.scanner.arm_glrt import ArmGlrtExecutionFailure, validate_native_output


def _digest(label: str) -> str:
    return sha256_digest(label.encode())


def _binding() -> ArmGlrtInputBindingV1:
    return ArmGlrtInputBindingV1.model_validate(
        {
            "input_sha256": _digest("manifest"),
            "ci16_sha256": _digest("ci16"),
            "receiver_ids": [0, 1],
            "dwells": [
                {
                    "dwell_index": 0,
                    "source_sample_start": 400,
                    "channel": 1,
                    "edge": "lower",
                    "actual_rf_hz": 10_709_687_500.0,
                }
            ],
        }
    )


def _payload(*, rows: list[dict[str, object]] | None = None, stride: int = 120) -> bytes:
    if rows is None:
        rows = [
            {
                "receiver_id": receiver,
                "probe_index": 0,
                "probe_start_ms": 0,
                "proposal_executed": 1,
                "proposal_tracking_fallback": 0,
                "proposal_neighbor_matches": 0,
                "candidate_count": 0,
                "retained_peak_count": 0,
                "coarse_gate_skipped_count": 0,
                "conditioned_fallback_count": 0,
                "actual_executed_glrt_calls": 0,
                "glrt_cache_hits": 0,
                "conditioned_cache_hits": 0,
                "fine_fft_cache_entries": 0,
                "fine_fft_cache_hits": 0,
                "fine_precision_calls": 0,
                "fine_precision_guard_checks": 0,
                "fine_precision_fallbacks": 0,
                "fine_precision_nonfinite_fallbacks": 0,
                "fine_precision_near_tie_fallbacks": 0,
                "fine_precision_interpolation_fallbacks": 0,
                "conditioned_bins_screened": 0,
                "conditioned_bins_rechecked": 0,
                "timings_ms": {
                    name: 0.0
                    for name in (
                        "total_cpu", "proposal", "stage_sum", "proposal_fold",
                        "proposal_correlation", "proposal_ranking", "coarse", "acquisition",
                        "fine_fft", "conditioned", "verification", "glrt",
                    )
                },
                "candidates": [],
            }
            for receiver in (0, 1)
        ]
    return json.dumps(
        {
            "schema": "leo-native-glrt/v1",
            "algorithm_id": "wave8-gate314-source-v1",
            "sample_rate_hz": 2_500_000,
            "dwell_ms": 120,
            "probe_ms": 20,
            "probe_stride_ms": stride,
            "rows": rows,
            "receiver_count": 2,
            "input_complex_times": 300_000,
            "template_complex_count": 3_333,
            "thread_safety": "process-serialized",
            "timings_ms": {"setup": 0.0, "detector_cpu": 1.0, "io": 0.0},
        }
    ).encode()


def test_arm_default_is_dense10_but_separate_from_scanner_contracts() -> None:
    assert ArmGlrtConfigurationV1(rate_hz=2_500_000).probe_stride_ms == 10
    assert ArmGlrtConfigurationV1(rate_hz=2_500_000, probe_stride_ms=120).probe_count == 1


@pytest.mark.parametrize(
    ("rate_hz", "dwell_ms", "probe_stride_ms"),
    tuple(
        itertools.product(
            (2_500_000, 5_000_000, 7_500_000, 10_000_000), (120, 240, 360), (10, 20, 120)
        )
    ),
)
def test_all_declared_rate_dwell_stride_configurations_are_opt_in_valid(
    rate_hz: int, dwell_ms: int, probe_stride_ms: int
) -> None:
    configuration = ArmGlrtConfigurationV1(
        rate_hz=rate_hz, dwell_ms=dwell_ms, probe_stride_ms=probe_stride_ms
    )
    assert configuration.probe_count >= 1


def test_validates_complete_ordered_native_inventory() -> None:
    result = validate_native_output(
        _payload(),
        configuration=ArmGlrtConfigurationV1(rate_hz=2_500_000, probe_stride_ms=120),
        input_binding=_binding(),
        native_binary_sha256=_digest("binary"),
        exact_template_sha256=_digest("exact"),
        control_template_sha256=_digest("control"),
    )
    assert result.rows[1].receiver_id == 1
    assert result.input_binding.dwells[0].source_sample_start == 400


def test_rejects_missing_row_instead_of_treating_it_as_candidate_absence() -> None:
    with pytest.raises(ArmGlrtExecutionFailure, match="cover the declared schedule"):
        validate_native_output(
            _payload(rows=[json.loads(_payload())["rows"][0]]),
            configuration=ArmGlrtConfigurationV1(rate_hz=2_500_000, probe_stride_ms=120),
            input_binding=_binding(),
            native_binary_sha256=_digest("binary"),
            exact_template_sha256=_digest("exact"),
            control_template_sha256=_digest("control"),
        )


def test_rejects_native_configuration_identity_mismatch() -> None:
    with pytest.raises(ArmGlrtExecutionFailure, match="configuration identity"):
        validate_native_output(
            _payload(stride=120),
            configuration=ArmGlrtConfigurationV1(rate_hz=2_500_000, probe_stride_ms=20),
            input_binding=_binding(),
            native_binary_sha256=_digest("binary"),
            exact_template_sha256=_digest("exact"),
            control_template_sha256=_digest("control"),
        )


def test_rejects_nonfinite_rf() -> None:
    binding = _binding().model_dump()
    dwell = binding["dwells"][0]
    dwell["actual_rf_hz"] = float("nan")
    with pytest.raises(ValueError, match="greater than"):
        ArmGlrtInputBindingV1.model_validate(binding)


def test_accepts_nullable_conditioned_frequency_from_host_native_output() -> None:
    """Candidate captured from the host `leo-native-glrt` executable."""
    fixture = (
        Path(__file__).parents[1] / "fixtures/arm_glrt/native-null-conditioned-cfo-candidate.json"
    )
    candidate = ArmGlrtCandidateV1.model_validate_json(fixture.read_bytes())
    assert candidate.conditioned_cfo_hz is None
    assert candidate.refinement_skipped is True
